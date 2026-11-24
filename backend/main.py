"""Punto de entrada principal para ejecutar la aplicacion Flask."""
from src import create_app

app = create_app()

if __name__ == "__main__":
    app.run()

