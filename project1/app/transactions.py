import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderItem, Product

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderItemRequest:
    product_id: int
    quantity: int


def place_order(session: Session, customer_id: int, items: list[OrderItemRequest]) -> int:
    if not items:
        raise ValueError("Заказ должен содержать хотя бы одну позицию")

    logger.info("Сценарий 1: размещение заказа для customer_id=%s", customer_id)
    try:
        # Явное начало транзакции: все операции внутри блока атомарны.
        with session.begin():
            customer = session.get(Customer, customer_id)
            if customer is None:
                raise ValueError(f"Клиент с ID={customer_id} не найден")

            # Шаг 1: создаем заказ с нулевой суммой.
            order = Order(customer_id=customer_id, order_date=datetime.utcnow(), total_amount=Decimal("0.00"))
            session.add(order)
            session.flush()

            # Шаг 2: добавляем позиции заказа.
            for item in items:
                if item.quantity <= 0:
                    raise ValueError(f"Количество для товара ID={item.product_id} должно быть больше 0")

                product = session.get(Product, item.product_id)
                if product is None:
                    raise ValueError(f"Товар с ID={item.product_id} не найден")

                subtotal = Decimal(product.price) * item.quantity
                order_item = OrderItem(
                    order_id=order.order_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    subtotal=subtotal,
                )
                session.add(order_item)
                logger.info(
                    "Добавлена позиция заказа: order_id=%s product_id=%s quantity=%s subtotal=%s",
                    order.order_id,
                    item.product_id,
                    item.quantity,
                    subtotal,
                )

            # flush нужен, т.к. в Session отключен autoflush.
            # Без него сумма может считаться по еще не отправленным в БД строкам.
            session.flush()

            # Шаг 3: пересчитываем итоговую сумму заказа.
            total = session.scalar(
                select(func.coalesce(func.sum(OrderItem.subtotal), 0)).where(OrderItem.order_id == order.order_id)
            )
            order.total_amount = Decimal(total)

        logger.info("Заказ %s успешно сохранен. total_amount=%s", order.order_id, order.total_amount)
        return order.order_id
    except Exception as exc:
        session.rollback()
        logger.exception("Транзакция размещения заказа завершилась ошибкой, выполнен rollback: %s", exc)
        raise


def update_customer_email(session: Session, customer_id: int, new_email: str) -> None:
    logger.info("Сценарий 2: обновление email для customer_id=%s", customer_id)
    try:
        # Явное начало транзакции: проверка и обновление происходят как единая операция.
        with session.begin():
            if not new_email or "@" not in new_email:
                raise ValueError("Некорректный формат email")

            existing = session.scalar(select(Customer).where(Customer.email == new_email))
            if existing is not None and existing.customer_id != customer_id:
                raise ValueError(f"Email '{new_email}' уже используется другим клиентом")

            customer = session.get(Customer, customer_id)
            if customer is None:
                raise ValueError(f"Клиент с ID={customer_id} не найден")

            customer.email = new_email

        logger.info("Email успешно обновлен для customer_id=%s", customer_id)
    except (ValueError, IntegrityError, SQLAlchemyError) as exc:
        session.rollback()
        logger.exception("Транзакция обновления email завершилась ошибкой, выполнен rollback: %s", exc)
        raise


def add_product(session: Session, product_name: str, price: Decimal) -> int:
    logger.info("Сценарий 3: добавление продукта product_name=%s price=%s", product_name, price)
    try:
        with session.begin():
            if not product_name or not product_name.strip():
                raise ValueError("Название продукта не может быть пустым")
            if price <= 0:
                raise ValueError("Цена должна быть больше 0")

            product = Product(product_name=product_name.strip(), price=price)
            session.add(product)
            session.flush()

        logger.info("Продукт %s успешно добавлен", product.product_id)
        return product.product_id
    except IntegrityError as exc:
        session.rollback()
        # Отдельно обрабатываем ошибку уникальности, чтобы сообщение было понятным для защиты.
        if "products_productname_key" in str(exc.orig):
            raise ValueError(f"Продукт с названием '{product_name}' уже существует") from exc
        logger.exception("Ошибка целостности при добавлении продукта, выполнен rollback: %s", exc)
        raise
    except (ValueError, IntegrityError, SQLAlchemyError) as exc:
        session.rollback()
        logger.exception("Транзакция добавления продукта завершилась ошибкой, выполнен rollback: %s", exc)
        raise

