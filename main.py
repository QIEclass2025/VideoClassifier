import sys
from PyQt5.QtWidgets import QApplication
from database import create_tables
from main_window import MainWindow

def main():
    """
    Main entry point for the Video Classifier application.
    """
    # Initialize the database and create tables if they don't exist
    print("Initializing database...")
    create_tables()
    
    # Create and run the PyQt application
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    print("Application started.")
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
