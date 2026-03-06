# simple.py - максимально простое приложение
from flask import Flask

simple_app = Flask(__name__)

@simple_app.route('/')
def home():
    return "ПРОСТОЕ ПРИЛОЖЕНИЕ РАБОТАЕТ!"

@simple_app.route('/test')
def test():
    return "Тестовый маршрут работает"

if __name__ == '__main__':
    simple_app.run(host='0.0.0.0', port=5000)