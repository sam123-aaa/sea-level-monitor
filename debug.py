from app import app

print("=== МАРШРУТЫ ===")
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint}: {rule.rule}")