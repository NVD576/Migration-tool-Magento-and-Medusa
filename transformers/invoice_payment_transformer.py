def _to_cents(value) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def transform_invoice(mg_invoice: dict, order_id: str = None) -> dict:
    """
    Transform Magento invoice to metadata format for Medusa
    Chỉ migrate metadata (không tạo invoice object trong Medusa)
    """
    return {
        "magento_invoice_id": mg_invoice.get("entity_id"),
        "magento_invoice_increment_id": mg_invoice.get("increment_id"),
        "magento_invoice_state": mg_invoice.get("state"),
        "magento_invoice_status": mg_invoice.get("state"),  # Magento dùng state
        "magento_invoice_total": str(_to_cents(mg_invoice.get("grand_total") or 0)),
        "magento_invoice_subtotal": str(_to_cents(mg_invoice.get("subtotal") or 0)),
        "magento_invoice_tax_amount": str(_to_cents(mg_invoice.get("tax_amount") or 0)),
        "magento_invoice_shipping_amount": str(_to_cents(mg_invoice.get("shipping_amount") or 0)),
        "magento_invoice_created_at": mg_invoice.get("created_at"),
        "magento_invoice_updated_at": mg_invoice.get("updated_at"),
    }


def transform_payment(mg_payment: dict, order_id: str = None) -> dict:
    """
    Transform Magento payment to metadata format for Medusa
    Chỉ migrate metadata: provider, txn_id, amount
    """
    # Xử lý additional_information (có thể là dict hoặc list)
    additional_info = mg_payment.get("additional_information", {})
    if isinstance(additional_info, list):
        # Nếu là list, tìm transaction_id trong các phần tử
        additional_info = {item.get("key"): item.get("value") for item in additional_info if isinstance(item, dict)}
    
    txn_id = (
        mg_payment.get("last_trans_id") or 
        mg_payment.get("transaction_id") or 
        additional_info.get("transaction_id") or
        additional_info.get("last_trans_id")
    )
    
    return {
        "magento_payment_method": mg_payment.get("method") or mg_payment.get("payment_method"),
        "magento_payment_provider": mg_payment.get("method") or mg_payment.get("payment_method"),
        "magento_payment_txn_id": txn_id,
        "magento_payment_amount": str(_to_cents(mg_payment.get("amount_ordered") or mg_payment.get("amount_paid") or 0)),
        "magento_payment_currency": mg_payment.get("currency_code"),
        "magento_payment_status": mg_payment.get("status"),
        "magento_payment_created_at": mg_payment.get("created_at"),
    }

