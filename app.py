from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Сервер работает! Если вы это видите - проблема в основном приложении."

@app.route('/test')
def test():
    return "✅ Тестовый маршрут работает."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)