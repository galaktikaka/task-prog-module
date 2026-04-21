CREATE TABLE IF NOT EXISTS customers (
    customerid SERIAL PRIMARY KEY,
    firstname VARCHAR(100) NOT NULL,
    lastname VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    productid SERIAL PRIMARY KEY,
    productname VARCHAR(255) NOT NULL UNIQUE,
    price DECIMAL(10,2) NOT NULL CHECK (price > 0)
);

CREATE TABLE IF NOT EXISTS orders (
    orderid SERIAL PRIMARY KEY,
    customerid INT NOT NULL REFERENCES customers(customerid),
    orderdate TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    totalamount DECIMAL(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orderitems (
    orderitemid SERIAL PRIMARY KEY,
    orderid INT NOT NULL REFERENCES orders(orderid) ON DELETE CASCADE,
    productid INT NOT NULL REFERENCES products(productid),
    quantity INT NOT NULL CHECK (quantity > 0),
    subtotal DECIMAL(10,2) NOT NULL CHECK (subtotal >= 0)
);

INSERT INTO customers (firstname, lastname, email) VALUES
('Alex', 'Johnson', 'alex.johnson@example.com'),
('Maria', 'Smirnova', 'maria.smirnova@example.com'),
('Ken', 'Tanaka', 'ken.tanaka@example.com')
ON CONFLICT (email) DO NOTHING;

INSERT INTO products (productname, price) VALUES
('Gaming Mouse', 59.99),
('USB-C Hub', 39.50),
('Laptop Stand', 89.00)
ON CONFLICT (productname) DO NOTHING;

