import pandas as pd
import json

# Load data
customers = pd.read_csv('customers.csv')
orders = pd.read_csv('orders.csv')
products = pd.read_csv('products.csv')

# Strip whitespace from string columns used in joins and filters
orders['Status'] = orders['Status'].str.strip()
orders['ProductID'] = orders['ProductID'].astype(str).str.strip()
products['ProductID'] = products['ProductID'].astype(str).str.strip()

# Filter orders to only those with Status == 'Delivered'
delivered_orders = orders[orders['Status'] == 'Delivered']

# Join delivered orders with products on ProductID to get Price
merged = pd.merge(delivered_orders, products[['ProductID', 'Price']], on='ProductID', how='left')

# Calculate total spent per order line
merged['LineTotal'] = merged['Quantity'] * merged['Price']

# Sum total spent per customer
total_spent_per_customer = merged.groupby('CustomerID')['LineTotal'].sum().reset_index()

# Find the customer with the maximum total spent
max_spent_row = total_spent_per_customer.loc[total_spent_per_customer['LineTotal'].idxmax()]

# Get customer details
customer_id = max_spent_row['CustomerID']
customer_info = customers[customers['CustomerID'] == customer_id].iloc[0]

# Prepare output
output = {
    'FirstName': customer_info['FirstName'],
    'LastName': customer_info['LastName'],
    'City': customer_info['City'],
    'TotalSpent': round(max_spent_row['LineTotal'], 2)
}

# Print output as JSON
print(json.dumps(output))