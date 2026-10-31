import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from audioworkbench.desktop import MainWindow
from audioworkbench.engine import ROOT
from PySide6.QtGui import QIcon


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('AudioWorkbench')
    app.setWindowIcon(QIcon(str(ROOT/'assets/app.ico')))
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('NaGeShuDai.AudioWorkbench')
    if "--self-test" in sys.argv:
        from audioworkbench.smoke import run
        return run(app,sys.argv[sys.argv.index("--self-test")+1])
    socket = QLocalSocket()
    socket.connectToServer('AudioWorkbench-local-v1')
    if socket.waitForConnected(250):
        socket.write(b'show'); socket.flush(); socket.waitForBytesWritten(250)
        return 0
    QLocalServer.removeServer('AudioWorkbench-local-v1')
    server = QLocalServer()
    server.listen('AudioWorkbench-local-v1')
    window = MainWindow()
    def activate():
        connection = server.nextPendingConnection()
        if connection: connection.deleteLater()
        window.showNormal(); window.raise_(); window.activateWindow()
    server.newConnection.connect(activate)
    window.show()
    return app.exec()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
