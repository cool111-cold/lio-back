from database import SaleDB, UserDB, ProductDB
from math import prod
import numpy as np
from numba import njit, prange
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from time import perf_counter

def _log(stage: str, ms: float) -> None:
    print(f"    [index] {stage}: {ms:.3f} ms")

def math_sale(price, sale):
    data = np.array([price], dtype=np.int32)
    result = np.zeros_like(data)
    percent = sell([sale])

    # Первый запуск — компиляция + вычисление
    calculate(data, percent, result)
    return int(result[0])

def get_user_products(db: Session, product_idx: list[int], sales: list[SaleDB], user: UserDB, partner_card: bool):
    products = []
    result_products = []

    # _t_fetch = perf_counter()
    # for product in product_idx:
    #     products.append({
    #         "product": db.query(ProductDB)
    #         .filter(ProductDB.id == product["product"])
    #         .first(),
    #         "quantity": product["quantity"],
    #     })
    # _log(f"get_user_products: fetch {len(product_idx)} products (N+1)", (perf_counter() - _t_fetch) * 1000)

    product_ids = [item["product"] for item in product_idx]

    products_db = (
        db.query(ProductDB)
        .filter(ProductDB.id.in_(product_ids))
        .all()
    )

    products_by_id = {
        product.id: product
        for product in products_db
    }

    products = [
        {
            "product": products_by_id[item["product"]],
            "quantity": item["quantity"],
        }
        for item in product_idx
    ]

    context = {
        "user": user,
        "product": None,
        "sale": None,
        "dt": datetime.now(),
        "weekday": datetime.now().weekday(),
    }

    _t_match = perf_counter()
    _cond_ms = 0.0
    _price_ms = 0.0
    _cond_calls = 0
    for product in products:
        local_price = product["product"].card_price if partner_card else product["product"].price
        context["product"] = product
        lk = {
            "product": product,
            "price": local_price,
            "sales": [],
            "final_price": local_price,
            "summ_price": 0
        }
        for sale in sales:
            discounts = []
            context["sale"] = sale
            if len(sale.condition) == 1:
                discounts.append(check_condition(sale.condition[0], context))
            else:
                for condition in sale.condition:
                    _t_c = perf_counter()

                    # context = {
                    #     "user": user,
                    #     "product": product,
                    #     "sale": sale,
                    #     "dt": datetime.now(),
                    #     "weekday": datetime.now().weekday(),
                    # }
                    discounts.append(check_condition(condition, context))
                    _cond_ms += (perf_counter() - _t_c) * 1000
                    _cond_calls += 1
            if all(discounts):
                lk["sales"].append(sale)
                # lk["final_price"] = math_sale(lk["final_price"], sale.discount)

        # логика по уникальности
        min_idx = [] if lk["sales"] == [] else min([sale.priority for sale in lk["sales"]])
        unic_sale = [sale for sale in lk["sales"] if sale.priority == min_idx and sale.summary == False]
        _t_p = perf_counter()
        lk["final_price"] = get_user_price(lk["final_price"], unic_sale if len(unic_sale) != 0 else lk["sales"])
        _price_ms += (perf_counter() - _t_p) * 1000
        if unic_sale != []:
            lk["sales"] = unic_sale
        else:
            lk["sales"] = [sale for sale in lk["sales"] if sale.summary == True]
        # -----

        lk["summ_price"] = lk["final_price"] * lk["product"]["quantity"]
        result_products.append(lk)

    _log(f"get_user_products: match sales (loop total)", (perf_counter() - _t_match) * 1000)
    _log(f"get_user_products:   -> check_condition x{_cond_calls}", _cond_ms)
    _log(f"get_user_products:   -> get_user_price (numba) x{len(products)}", _price_ms)

    return result_products

def get_final_price(sales: list[SaleDB], user: UserDB, promocode: str, ball: int, final_price: float):
    final_sales = []
    context = {
        "user": user,
        "price": final_price,
        "promocode": promocode,
    }
    _t_match = perf_counter()
    for sale in sales:
        discounts = []
        for condition in sale.condition:
            context["sale"] = sale
            discounts.append(check_condition(condition, context))

        if all(discounts):
            final_sales.append(sale)
    _log("get_final_price: match sales", (perf_counter() - _t_match) * 1000)

    min_idx = [] if final_sales == [] else min([sale.priority for sale in final_sales])
    unic_sale = [sale for sale in final_sales if sale.priority == min_idx and sale.summary == False]
    if len(unic_sale) != 0:
        final_sales = unic_sale
    else:
        final_sales = [sale for sale in final_sales if sale.summary == True]

    _t_p = perf_counter()
    price = get_user_price(final_price, final_sales) - ball
    _log("get_final_price: get_user_price (numba)", (perf_counter() - _t_p) * 1000)
    return final_sales, price

def get_user_product_cards(db: Session, param_datetime: Optional[datetime] = None):
    now = param_datetime or datetime.now()
    _t = perf_counter()
    cards = (
        db.query(SaleDB)
        .filter(
            SaleDB.active == True,
            SaleDB.started_at <= now,
            SaleDB.ended_at >= now,
            SaleDB.isProduct == True,
        )
        .order_by(SaleDB.priority.asc())
        .all()
    )
    _log(f"get_user_product_cards: SQL query ({len(cards)} rows)", (perf_counter() - _t) * 1000)
    return cards

def get_user_cards(db: Session, param_datetime: Optional[datetime] = None):
    now = param_datetime or datetime.now()
    _t = perf_counter()
    cards = (
        db.query(SaleDB)
        .filter(
            SaleDB.active == True,
            SaleDB.started_at <= now,
            SaleDB.ended_at >= now,
            SaleDB.isProduct == False,
        )
        .order_by(SaleDB.priority.asc())
        .all()
    )
    _log(f"get_user_cards: SQL query ({len(cards)} rows)", (perf_counter() - _t) * 1000)
    return cards


@njit(fastmath=True, parallel=True)
def calculate(arr, percent_scaled, result):
    # Так как процент scaled (умножен на 100), нам нужно делить не на 100, а на 10 000.
    # Новая магическая константа для деления на 10 000 через сдвиг >> 32:
    # 2^32 / 10000 = 429496.7296 -> округляем до 429497
    magic_const = 429497

    for i in prange(len(arr)):
        # Все вычисления снова происходят строго в целых числах (int)
        discounted = (arr[i] * percent_scaled * magic_const) >> 32
        result[i] = arr[i] - discounted


def sell(y):
    skid = 1 - prod([1 - i for i in y])
    # Возвращаем процент, умноженный на 100, и приводим к int (например, 43.75% станет 4375)
    return int(round(skid * 100 * 100))


def get_value(field: str, context: dict):
    value = context

    for part in field.split("."):
        if isinstance(value, dict):
            value = value[part]
        else:
            value = getattr(value, part)

    return value

def resolve_value(value, context):
    if isinstance(value, str) and "." in value:
        return get_value(value, context)

    return value

def check_condition(condition: dict, context: dict):
    field = condition["field"]
    operator = condition["operator"]
    expected = condition["value"]

    actual = get_value(field, context)
    result = resolve_value(expected, context)

    if operator == "==":
        return actual == result

    if operator == "!=":
        return actual != result

    if operator == ">":
        return actual > result

    if operator == "<":
        return actual < result

    if operator == ">=":
        return actual >= result

    if operator == "<=":
        return actual <= result

    return False


def get_discount(user: UserDB, products: list[ProductDB], sales: list[SaleDB]):
    discounts = []
    for sale in sales:
        for condition in sale.condition:
            if 'product' in condition["field"] or 'product' in condition["value"]:
                for product in products:
                    context = {
                        "user": user,
                        "product": product,
                        "sale": sale,
                    }
                    if check_condition(condition, context):
                        discounts.append(sale)
            else:
                context = {
                    "user": user,
                    "product": products[0],
                    "sale": sale,
                }
                if check_condition(condition, context):
                    discounts.append(sale)
    return discounts

_numba_compiled = False

def get_user_price(price: int, sales: list[SaleDB]):
    global _numba_compiled
    # Один элемент
    data = np.array([price], dtype=np.int32)
    result = np.zeros_like(data)
    percent = sell([sale.discount for sale in sales])

    # Первый запуск — компиляция + вычисление
    _t = perf_counter()
    calculate(data, percent, result)
    _dt = (perf_counter() - _t) * 1000
    if not _numba_compiled:
        _log("get_user_price: numba calculate() FIRST CALL (JIT compile)", _dt)
        _numba_compiled = True
    elif _dt > 1.0:
        _log("get_user_price: numba calculate()", _dt)

    return int(result[0])