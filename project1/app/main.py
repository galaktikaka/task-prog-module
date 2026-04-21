import logging
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import get_session, wait_for_database
from app.transactions import OrderItemRequest, add_product, place_order, update_customer_email


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def print_rows(title: str, query: str) -> None:
    with get_session() as session:
        rows = session.execute(text(query)).mappings().all()
    print(f"\n{title}")
    for row in rows:
        print(dict(row))


def run_demo() -> None:
    logger = logging.getLogger(__name__)

    # Сценарий 1: транзакция создания заказа.
    with get_session() as session:
        order_id = place_order(
            session=session,
            customer_id=1,
            items=[OrderItemRequest(product_id=1, quantity=2), OrderItemRequest(product_id=2, quantity=1)],
        )
        logger.info("Сценарий 1 завершен. order_id=%s", order_id)

    print_rows(
        "Orders after Scenario 1",
        "SELECT orderid, customerid, orderdate, totalamount FROM orders ORDER BY orderid",
    )
    print_rows(
        "OrderItems after Scenario 1",
        "SELECT orderitemid, orderid, productid, quantity, subtotal FROM orderitems ORDER BY orderitemid",
    )

    # Сценарий 2: транзакция обновления email клиента.
    with get_session() as session:
        update_customer_email(session=session, customer_id=1, new_email="updated.alex@example.com")
        logger.info("Сценарий 2 завершен")

    print_rows(
        "Customers after Scenario 2",
        "SELECT customerid, firstname, lastname, email FROM customers ORDER BY customerid",
    )

    # Сценарий 3: транзакция добавления нового продукта.
    with get_session() as session:
        product_id = add_product(session=session, product_name="Mechanical Keyboard", price=Decimal("149.99"))
        logger.info("Сценарий 3 завершен. product_id=%s", product_id)

    print_rows(
        "Products after Scenario 3",
        "SELECT productid, productname, price FROM products ORDER BY productid",
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    try:
        wait_for_database()
        run_demo()
        logger.info("Все сценарии успешно выполнены")
    except SQLAlchemyError:
        logger.exception("Ошибка SQLAlchemy во время выполнения демо")
        raise
    except Exception:
        logger.exception("Непредвиденная ошибка во время выполнения демо")
        raise


if __name__ == "__main__":
    main()

