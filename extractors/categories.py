def extract_categories(magento_connector):
    def _flatten_tree(node: dict):
        out = [node]
        for child in (node.get("children_data") or []):
            out.extend(_flatten_tree(child))
        return out

    page = 1
    all_categories = []

    while True:
        if hasattr(magento_connector, "get_category_tree"):
            result = magento_connector.get_category_tree()
        else:
            result = magento_connector.get_categories(page=page)

        items = result.get("items")
        if isinstance(items, list):
            if not items:
                break
            all_categories.extend(items)
            page += 1
            continue

        if "children_data" in result:
            all_categories.extend(_flatten_tree(result))
        break

    filtered = []
    for c in all_categories:
        if c.get("id") == 1 or c.get("level") in (0, "0"):
            continue
        filtered.append(c)

    return filtered


