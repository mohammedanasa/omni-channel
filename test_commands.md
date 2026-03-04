## Testing

Before testing, Make sure to comment the following in middleware. if it's not commented, the auth will fail.
```bash
django_tenants.middleware.main.TenantMainMiddleware
```

### To run 

```bash
pytests filepath/filename.py -s
```

### Test particular function
```bash
pytest tests/products/test_products.py::TestProduct::test_create_product_with_nonexistent_category -s
```