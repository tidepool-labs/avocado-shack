"""Stateful in-memory Clover v3 transport for synthetic inventory tests."""
import json
import re
from copy import deepcopy

from hass.clover.client import ID, Request, Response
from hass.clover.transport import _norm


class FakeClover:
    """Seed with iterables of Clover JSON item and category records (no page wrappers).

    An item's optional expanded itemStock seeds both stock endpoints. The fake
    uses a deterministic millisecond clock, starting after the seeded inventory.
    """

    def __init__(self, merchant="FAKEMERCH0001", items=(), categories=()):
        self._merchant = merchant
        self._items = {item["id"]: deepcopy(item) for item in items}
        self._categories = {cat["id"]: deepcopy(cat) for cat in categories}
        self._time = max((max(item.get("modifiedTime", 0),
                              (item.get("itemStock") or {}).get("modifiedTime", 0))
                          for item in self._items.values()), default=0)
        self._next_id = 1
        self._failure = None
        self._lose = False
        self.log = []

    def __call__(self, request: Request) -> Response:
        path, pairs = _norm(request.url)
        query = dict(pairs)
        match = re.fullmatch(rf"/v3/merchants/({ID})(/.*)?", path)
        route = (match[2] or "") if match else ""
        detail = re.fullmatch(rf"/(items|item_stocks)/({ID})", route)
        # Only keep known route literals in their fixed positions. Unknown
        # segments could be IDs even when the request won't match a route.
        parts = path.split("/")
        template_parts = ["{id}" if part else "" for part in parts]
        if parts[:3] == ["", "v3", "merchants"]:
            template_parts[:3] = parts[:3]
            if len(parts) > 4 and parts[4] in ("items", "item_stocks", "categories", "category_items"):
                template_parts[4] = parts[4]
        template = "/".join(template_parts)
        try:
            body = json.loads(request.body) if request.body is not None else None
        except ValueError:
            body = None
        self.log.append((request.method, template, body))
        if self._failure is not None:
            status, self._failure = self._failure, None
            return self._reply(status)
        if not match or match[1] != self._merchant:
            return self._reply(405)
        item_id = detail[2] if detail else None
        if request.method == "GET":
            return self._get(route, item_id, query)
        resource = detail[1] if detail else None
        if ((request.method == "POST" and (route in ("/items", "/category_items") or resource == "items")) or
                (request.method == "PUT" and resource == "item_stocks")):
            if not isinstance(body, dict):
                return self._reply(400)
            return self._write(route, item_id, deepcopy(body))
        return self._reply(405)

    @staticmethod
    def _reply(status, data=None):
        return Response(status, body=json.dumps({} if data is None else data).encode())

    @staticmethod
    def _expanded(item, query):
        expand = query.get("expand", "").split(",")
        return {k: v for k, v in item.items()
                if k not in ("itemStock", "categories", "tags") or k in expand}

    def _get(self, route, item_id, query):
        if route == "":
            return self._reply(200, {"id": self._merchant, "name": "Fake Test Shop",
                                     "currency": "USD", "isBillable": False})
        if item_id is not None:
            item = self._items.get(item_id)
            if item is not None:
                doc = item.get("itemStock") if route.startswith("/item_stocks/") else self._expanded(item, query)
                if doc is not None:
                    return self._reply(200, doc)
            return self._reply(404)
        if route == "/items":
            items = self._items.values()
            condition = query.get("filter", "")
            if condition.startswith("sku="):
                items = [item for item in items if item.get("sku") == condition[4:]]
            elif condition.startswith("modifiedTime>="):
                since = int(condition.removeprefix("modifiedTime>="))
                items = [item for item in items if item.get("modifiedTime", 0) >= since]
            rows = [self._expanded(item, query) for item in items]
        elif route == "/item_stocks":
            rows = [item["itemStock"] for item in self._items.values() if item.get("itemStock") is not None]
        elif route == "/categories":
            rows = list(self._categories.values())
        else:
            return self._reply(405)
        offset = int(query.get("offset", 0))
        limit = int(query.get("limit", 1000))
        return self._reply(200, {"elements": rows[offset:offset + limit]})

    def _write(self, route, item_id, body):
        status = 200
        if route == "/items":
            while True:
                item_id = f"FAKEITEM{self._next_id:05d}"
                self._next_id += 1
                if item_id not in self._items:
                    break
            result = self._items[item_id] = {**body, "id": item_id}
            self._touch(result)
            status = 201
        elif route == "/category_items":
            links = [(link["item"]["id"], link["category"]["id"]) for link in body["elements"]]
            if any(i not in self._items or c not in self._categories for i, c in links):
                return self._reply(404)
            for i, c in links:
                item = self._items[i]
                cats = item.setdefault("categories", {"elements": []})["elements"]
                if not any(cat["id"] == c for cat in cats):
                    cats.append({"id": c, "name": self._categories[c]["name"]})
                self._touch(item)
            result = body
        else:
            item = self._items.get(item_id)
            if item is None:
                return self._reply(404)
            if route.startswith("/item_stocks/"):
                result = self._set_stock(item, body["quantity"])
            else:
                item.update({k: v for k, v in body.items() if k not in ("id", "itemStock", "modifiedTime")})
                self._touch(item)
                result = item
        if self._lose:
            self._lose = False
            raise OSError("fake Clover lost the write response")
        return self._reply(status, result)

    def _touch(self, item):
        self._time += 1
        item["modifiedTime"] = self._time

    def _set_stock(self, item, quantity):
        self._touch(item)
        stock = {**(item.get("itemStock") or {}), "item": {"id": item["id"]},
                 "quantity": quantity, "modifiedTime": self._time}
        item["itemStock"] = stock
        return stock

    def sell(self, item_id, n):
        item = self._items[item_id]
        self._set_stock(item, item["itemStock"]["quantity"] - n)

    def fail_next(self, status):
        if not 400 <= status <= 599:
            raise ValueError("expected a 4xx or 5xx status")
        self._failure = status

    def lose_next_response(self):
        self._lose = True

    def register_search(self, text):
        return [deepcopy(item) for item in self._items.values()
                if not (item.get("hidden") or item.get("deleted")) and
                (text.casefold() in item.get("name", "").casefold() or
                 text in (item.get("sku"), item.get("code")))]
