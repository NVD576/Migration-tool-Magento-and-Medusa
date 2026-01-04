import json
import requests
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector
from extractors.orders import extract_orders, extract_order_invoices, extract_order_payments
from transformers.order_transformer import transform_order, calculate_checksum
from transformers.invoice_payment_transformer import transform_invoice, transform_payment
from migrators.utils import (
    _limit_iter, _fetch_all_variants, _is_duplicate_http, 
    _resp_json_or_text, log_dry_run, handle_medusa_api_error,
    get_timestamp, log_info, log_success, log_warning, log_error, log_section, log_summary,
    get_timestamp, log_info, log_success, log_warning, log_error, log_section, log_summary,
    check_stop_signal, check_pause_signal
)


def _validate_checksum(payload, mg_order):
    """
    Validate checksum: Sum(line_total) + tax + shipping = grand_total
    Returns: (is_valid, calculated_total, expected_total, details)
    """
    items = payload.get("items", [])
    metadata = payload.get("metadata", {})
    
    tax_amount = int(metadata.get("magento_tax_amount", 0))
    shipping_amount = int(metadata.get("magento_shipping_amount", 0))
    grand_total = int(metadata.get("magento_grand_total", 0))
    
    calculated_total, line_total = calculate_checksum(items, tax_amount, shipping_amount)
    
    # Cho phép sai số 1 cent do làm tròn
    is_valid = abs(calculated_total - grand_total) <= 1
    
    details = {
        "line_total": line_total,
        "tax_amount": tax_amount,
        "shipping_amount": shipping_amount,
        "calculated_total": calculated_total,
        "expected_total": grand_total,
        "difference": abs(calculated_total - grand_total),
    }
    
    return is_valid, calculated_total, grand_total, details


def _sync_single_order_with_retry(order, magento: MagentoConnector, medusa: MedusaConnector, args, region_id, sku_map, shipping_option, max_retries=3):
    """
    Sync single order with retry mechanism and rollback support
    """
    inc = order.get("increment_id") or order.get("entity_id")
    order_id = order.get("entity_id")
    
    log_info(f"Syncing order: {inc}")
    
    # STEP 1: Transform order
    log_info(f"   [STEP 1] Mapping data & SKUs...", indent=1)
    payload = transform_order(order, region_id, sku_map, shipping_option)
    
    # STEP 1.5: Validate checksum
    checksum_valid, calc_total, exp_total, checksum_details = _validate_checksum(payload, order)
    if not checksum_valid:
        log_warning(f"   ⚠️ Checksum mismatch for order {inc}:", indent=1)
        log_warning(f"      Calculated: {calc_total}, Expected: {exp_total}, Diff: {checksum_details['difference']}", indent=1)
        log_warning(f"      Line Total: {checksum_details['line_total']}, Tax: {checksum_details['tax_amount']}, Shipping: {checksum_details['shipping_amount']}", indent=1)
        # Vẫn tiếp tục nhưng ghi log warning
        payload["metadata"]["magento_checksum_warning"] = "true"
    else:
        log_success(f"   ✅ Checksum validated: {calc_total} = {exp_total}", indent=1)
    
    log_dry_run(payload, "order", args)
    if args.dry_run:
        return ('ignore', "Dry run enabled")
    
    # STEP 2: Extract invoices and payments (optional)
    invoice_metadata = {}
    payment_metadata = {}
    
    if getattr(args, 'migrate_invoices', False):
        try:
            log_info(f"   [STEP 1.5] Extracting invoices...", indent=1)
            invoices = extract_order_invoices(magento, order_id)
            if invoices:
                # Lấy invoice đầu tiên hoặc merge tất cả
                invoice = invoices[0]
                invoice_metadata = transform_invoice(invoice, order_id)
                log_success(f"   ✅ Found {len(invoices)} invoice(s)", indent=1)
        except Exception as e:
            log_warning(f"   ⚠️ Failed to extract invoices: {e}", indent=1)
    
    if getattr(args, 'migrate_payments', False):
        try:
            log_info(f"   [STEP 1.6] Extracting payments...", indent=1)
            payments = extract_order_payments(magento, order_id)
            if payments:
                # Lấy payment đầu tiên hoặc merge tất cả
                payment = payments[0] if isinstance(payments, list) else payments
                payment_metadata = transform_payment(payment, order_id)
                log_success(f"   ✅ Found payment data", indent=1)
        except Exception as e:
            log_warning(f"   ⚠️ Failed to extract payments: {e}", indent=1)
    
    # Merge invoice và payment metadata vào order metadata
    if invoice_metadata:
        payload["metadata"].update(invoice_metadata)
    if payment_metadata:
        payload["metadata"].update(payment_metadata)
    
    # STEP 3: Create draft order with retry
    draft_id = None
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                log_info(f"   [RETRY {attempt}/{max_retries}] Creating Draft Order...", indent=1)
                time.sleep(1 * attempt)  # Exponential backoff
            else:
                log_info(f"   [STEP 2] Creating Draft Order...", indent=1)
            
            res = medusa.create_draft_order(payload, idempotency_key=f"order:{inc}")
            draft = res.get("draft_order") or res.get("draftOrder") or res
            draft_id = draft.get("id") if isinstance(draft, dict) else None
            
            if draft_id:
                log_success(f"   ✅ Draft Order created: {draft_id}", indent=1)
                break
                
        except requests.exceptions.HTTPError as e:
            last_error = e
            resp = getattr(e, "response", None)
            
            # Nếu là duplicate, không retry
            if _is_duplicate_http(resp):
                status_tuple = handle_medusa_api_error(e, "Draft Order", inc)
                return status_tuple if isinstance(status_tuple, tuple) else (status_tuple, str(e))
            
            # Nếu là lỗi client (4xx), không retry
            if resp and 400 <= resp.status_code < 500:
                log_error(f"   ❌ Client error (HTTP {resp.status_code}), skipping retry", indent=1)
                status_tuple = handle_medusa_api_error(e, "Draft Order", inc)
                return status_tuple if isinstance(status_tuple, tuple) else (status_tuple, str(e))
            
            # Server error (5xx), retry
            if attempt < max_retries:
                log_warning(f"   ⚠️ Server error (HTTP {resp.status_code if resp else 'unknown'}), retrying...", indent=1)
            else:
                log_error(f"   ❌ Failed after {max_retries} attempts", indent=1)
                status_tuple = handle_medusa_api_error(e, "Draft Order", inc)
                return status_tuple if isinstance(status_tuple, tuple) else (status_tuple, str(e))
                
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                log_warning(f"   ⚠️ Error: {str(e)}, retrying...", indent=1)
                time.sleep(1 * attempt)
            else:
                log_error(f"   ❌ Failed after {max_retries} attempts: {str(e)}", indent=1)
                return ('fail', str(e))
    
    if not draft_id:
        return ('fail', f"Failed to create draft order after {max_retries} attempts: {str(last_error)}")
    
    # STEP 4: Finalize order (if enabled)
    if draft_id and getattr(args, 'finalize_orders', False):
        try:
            log_info(f"   [STEP 3] Finalizing order...", indent=1)
            finalized = medusa.finalize_draft_order(draft_id)
            
            if finalized is None:
                log_warning(f"   ⚠️ Draft Order {draft_id} created. Finalize not supported/returned empty.", indent=1)
            else:
                log_success(f"   ✅ Finalized Order: {draft_id}", indent=1)
                
                # Try to create fulfillment
                try:
                    medusa.create_fulfillment(draft_id, draft.get("items") or [])
                    log_success(f"   ✅ Created fulfillment for order {draft_id}", indent=1)
                except Exception as fe:
                    log_warning(f"   ⚠️ Failed to create fulfillment: {fe}", indent=1)
                    
        except requests.exceptions.HTTPError as fe:
            log_warning(f"   ⚠️ Draft Order {draft_id} created, but Finalize failed.", indent=1)
            resp = getattr(fe, "response", None)
            if resp and resp.status_code == 500:
                log_warning("   (Server Error 500 during finalize. Likely an inventory bug. Saved as Draft.)", indent=1)
            else:
                status_code = resp.status_code if resp else 'unknown'
                log_error(f"   Status: {status_code}", indent=1)
                if resp:
                    error_text = _resp_text(resp)
                    log_error(f"   Response: {error_text[:200]}", indent=1)
                else:
                    log_error(f"   Error details: {str(fe)}", indent=1)
            
            # Rollback: Xóa draft order nếu finalize thất bại và rollback được bật
            if getattr(args, 'rollback_on_finalize_fail', False):
                try:
                    log_warning(f"   [ROLLBACK] Attempting to delete draft order {draft_id}...", indent=1)
                    medusa.delete_draft_order(draft_id)
                    log_success(f"   ✅ Rollback successful: Draft order {draft_id} deleted", indent=1)
                except requests.exceptions.HTTPError as rb_e:
                    resp = getattr(rb_e, "response", None)
                    status_code = resp.status_code if resp else 'unknown'
                    log_error(f"   ❌ Rollback failed (HTTP {status_code}): {str(rb_e)}", indent=1)
                    if resp:
                        error_text = _resp_text(resp)
                        log_error(f"   Response: {error_text[:200]}", indent=1)
                except Exception as rb_e:
                    log_error(f"   ❌ Rollback failed: {str(rb_e)}", indent=1)
            
            return ('success', f"Draft created but finalize failed: {str(fe)}")
        except Exception as e:
            log_error(f"   ❌ Finalize error: {str(e)}", indent=1)
            log_error(f"   Error type: {type(e).__name__}", indent=1)
            # Rollback nếu có exception không phải HTTPError
            if getattr(args, 'rollback_on_finalize_fail', False):
                try:
                    log_warning(f"   [ROLLBACK] Exception during finalize. Attempting to delete draft order {draft_id}...", indent=1)
                    medusa.delete_draft_order(draft_id)
                    log_success(f"   ✅ Rollback successful: Draft order {draft_id} deleted", indent=1)
                except Exception as rb_e:
                    log_error(f"   ❌ Rollback failed: {str(rb_e)}", indent=1)
            return ('success', f"Draft created but finalize error: {str(e)}")
    elif draft_id:
        log_success(f"   ✅ Created Draft Order: {draft_id} (Not finalized)", indent=1)
    
    return ('success', None)


def migrate_orders(magento: MagentoConnector, medusa: MedusaConnector, args, migration_state=None):
    log_section("ORDER MIGRATION PHASE")
    
    # Check stop requested before starting
    if (migration_state and migration_state.get('stop_requested')) or check_stop_signal():
        log_warning("Migration stopped by user before starting order migration.")
        return
        
    # PAUSE CHECK
    if check_pause_signal(): return
    
    # Delta migration support
    updated_at_from = None
    if getattr(args, 'delta_migration', False) and getattr(args, 'delta_from_date', None):
        updated_at_from = args.delta_from_date
        log_info(f"Delta migration enabled: Only migrating orders updated after {updated_at_from}")
    
    log_info("Fetching orders from Magento...")
    orders = extract_orders(magento, updated_at_from=updated_at_from)
    
    if getattr(args, "order_ids", None):
        order_ids = {x.strip() for x in str(args.order_ids).split(",") if x.strip()}
        log_info(f"Filter by IDs: {order_ids}", indent=1)
        orders = [o for o in orders if str(o.get("entity_id")) in order_ids or str(o.get("increment_id")) in order_ids]
    
    orders = _limit_iter(orders, args.limit)
    order_count = len(orders)
    log_info(f"Found {order_count} orders to migrate...\n")
    
    if order_count == 0:
        log_warning("No orders to migrate.")
        return
    
    # STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    # Get region
    region_id = None
    try:
        regions_res = medusa.get_regions()
        regions = regions_res.get("regions") or regions_res.get("data") or []
        if regions:
            region_id = regions[0].get("id")
            log_success(f"Using region: {regions[0].get('name', 'Unknown')} ({region_id})", indent=1)
    except Exception as e:
        log_error(f"Failed to get regions: {e}")
    
    if not region_id:
        log_error("Could not get region_id from Medusa (/admin/regions). Skipping orders.")
        return
    
    # STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    # Get SKU map
    log_info("Fetching existing variants from Medusa...")
    all_variants = _fetch_all_variants(medusa)
    sku_map = {v.get("sku"): v.get("id") for v in all_variants if v.get("sku") and v.get("id")}
    log_success(f"Found {len(sku_map)} variants for mapping.", indent=1)
    
    # STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    # Get shipping option
    log_info("Fetching shipping options...")
    shipping_option = None
    try:
        so_res = medusa.list_shipping_options(limit=20)
        so_items = so_res.get("shipping_options") or so_res.get("data") or []
        if so_items:
            so = so_items[0]
            shipping_option = {"id": so.get("id"), "name": so.get("name") or "Standard Shipping"}
            log_success(f"Using shipping option: {shipping_option['id']} ({shipping_option['name']})", indent=1)
        else:
            log_warning("No shipping options found. Order finalization might fail.", indent=1)
    except Exception as e:
        log_warning(f"Failed to fetch shipping options: {e}", indent=1)
    
    # STOP CHECK
    if check_pause_signal(): return
    if check_stop_signal(): return

    count_success = 0
    count_ignore = 0
    count_fail = 0
    checksum_mismatches = 0
    
    log_info("Starting transformation & sync process...\n")
    
    with ThreadPoolExecutor(max_workers=args.max_workers or 10) as executor:
        futures = {
            executor.submit(_sync_single_order_with_retry, o, magento, medusa, args, region_id, sku_map, shipping_option): o
            for o in orders
        }
        
        processed_count = 0
        processed_count = 0
        for future in as_completed(futures):
            # Check pause signal
            if check_pause_signal(): pass

            # Check stop requested
            if (migration_state and migration_state.get('stop_requested')) or check_stop_signal():
                log_warning("🛑 Stop requested by user. Cancelling remaining tasks...")
                # Cancel pending futures
                for f in futures:
                    if not f.done():
                        f.cancel()
                log_warning(f"Migration stopped. Processed {processed_count}/{order_count} orders before stop.")
                break
            
            processed_count += 1
            order = futures[future]
            inc = order.get("increment_id") or order.get("entity_id")
            
            try:
                res_tuple = future.result()
                if isinstance(res_tuple, tuple):
                    status, reason = res_tuple
                else:
                    status, reason = res_tuple, None
                
                if status == 'success':
                    count_success += 1
                    # Check if checksum warning
                    payload = transform_order(order, region_id, sku_map, shipping_option)
                    checksum_valid, _, _, _ = _validate_checksum(payload, order)
                    if not checksum_valid:
                        checksum_mismatches += 1
                elif status == 'ignore':
                    count_ignore += 1
                else:
                    count_fail += 1
            except Exception as e:
                log_error(f"Unexpected error for '{inc}': {e}")
                count_fail += 1
            
            if processed_count % 5 == 0 or processed_count == order_count:
                log_info(f"Progress: {processed_count}/{order_count} orders processed...")
    
    log_summary("Order Migration", count_success, count_ignore, count_fail)
    
    if checksum_mismatches > 0:
        log_warning(f"⚠️ Checksum mismatches detected: {checksum_mismatches} orders")
        log_warning("   Please review these orders manually for data integrity.")
