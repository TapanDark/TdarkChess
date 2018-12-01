import argparse
import logging
import socket
import sys
import random
import threading

import chess
import chess.svg
from PyQt4.QtCore import pyqtSlot, Qt
from PyQt4.QtGui import QApplication, QWidget, QLabel
from PyQt4.QtSvg import QSvgWidget


class _ColoredFormatter(logging.Formatter):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = map(lambda x: 30 + x, range(8))
    COLORS = {
        'WARNING': YELLOW,
        'DEBUG': BLUE,
        'CRITICAL': MAGENTA,
        'ERROR': RED,
    }
    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[1;%dm"

    def __init__(self, *args, **kwargs):
        logging.Formatter.__init__(self, *args, **kwargs)

    def format(self, record):
        msg = logging.Formatter.format(self, record)
        if record.levelname in self.COLORS:
            msg = self.COLOR_SEQ % self.COLORS[record.levelname] + msg + self.RESET_SEQ
        return msg


def _formatter(enableColor=True, logLevel=logging.DEBUG if sys.flags.debug else logging.INFO):
    _logFormatDebug = '%(asctime)s: %(levelname)s: Function %(funcName)s: Line %(lineno)s: File %(filename)s: %(message)s'
    _logFormat = '%(asctime)s: %(levelname)s: %(message)s' if sys.flags.debug == 0 else _logFormatDebug
    _dateFormat = '%m/%d/%Y %H:%M:%S'
    if logLevel == logging.DEBUG:
        logFormat = _logFormatDebug
    else:
        logFormat = _logFormat
    if enableColor:
        formatter = _ColoredFormatter(logFormat, datefmt=_dateFormat)
    else:
        formatter = logging.Formatter(logFormat, datefmt=_dateFormat)
    return formatter


def setBasicConfig(logLevel=logging.DEBUG if sys.flags.debug else logging.INFO, enableColor=True):
    logger = logging.root
    logger.setLevel(logLevel)
    streamHandle = logging.StreamHandler(sys.stdout)
    streamHandle.setLevel(logLevel)
    streamHandle.setFormatter(_formatter(enableColor, logLevel))
    logger.addHandler(streamHandle)


class MainWindow(QWidget):
    def __init__(self, c960=False, ip=None, port=5000, size=500):
        super(MainWindow, self).__init__()
        self.is960 = c960
        self.setWindowTitle("TDark Chess %s" % (ip if ip else "server"))
        self.widgetSvg = QSvgWidget(parent=self)
        self.coordinates = True
        self.resizeWindow(300, 300, size, size)
        if self.is960:
            self.chessboard = chess.Board.from_chess960_pos(random.randint(0, 959))
        else:
            self.chessboard = chess.Board()
        self.pieceToMove = [None, None]
        if ip:
            self.flipped = True
            self.isMyMove = False
        else:
            self.flipped = False
            self.isMyMove = True
        self.lastMove = None
        self.check = None
        self.lastReceived = None
        self.connectNetwork(ip, port)

    def resizeWindow(self, topX, topY, width, height):
        logging.info("TopX: %s, TopY:%s, width:%s, height:%s" % (topX, topY, width, height))
        width = max(width, 200)
        height = max(height, 200)
        self.windowSize = min(width, height)
        self.cbSize = int(self.windowSize * 0.75)
        # see chess.svg.py line 129
        self.margin = 0.05 * self.cbSize if self.coordinates == True else 0
        self.squareSize = (self.cbSize - 2 * self.margin) / 8.0
        self.svgX = int(self.cbSize / 8)  # top left x-pos of chessboard
        self.svgY = int(self.cbSize / 8)  # top left y-pos of chessboard
        self.widgetSvg.setGeometry(self.svgX, self.svgY, self.cbSize, self.cbSize)
        self.setGeometry(topX, topY, width, height)

    def _socketReader(self, socketObj):
        while True:
            self.lastReceived = socketObj.recv(1024)
            logging.info("RECEIVED %s" % self.lastReceived)
            if not self.isMyMove:
                if self.performMove(self.lastReceived):
                    self.isMyMove = True
                    logging.info("My Move:%s" % self.isMyMove)

    def connectNetwork(self, ip, port):
        if not ip:
            # server mode
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.serverSocket.bind(('0.0.0.0', port))
            self.serverSocket.listen(5)
            (self.appSocket, address) = self.serverSocket.accept()
            fen = self.chessboard.fen(shredder=False)
            logging.critical("FEN %s" % fen)
            self.appSocket.send(fen)
            ct = threading.Thread(target=self._socketReader, args=[self.appSocket])
        else:
            # client mode
            self.appSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.appSocket.connect((ip, port))
            fen = self.appSocket.recv(1024)
            logging.critical("FEN %s" % fen)
            self.chessboard = chess.Board(fen=fen, chess960=self.is960)
            ct = threading.Thread(target=self._socketReader, args=[self.appSocket])
        ct.setDaemon(True)
        ct.start()

    def getPostFromCoordinates(self, x, y):
        file = int((x - (self.svgX + self.margin)) / self.squareSize)
        rank = 7 - int((y - (self.svgY + self.margin)) / self.squareSize)
        if self.flipped:
            file = 7 - file
            rank = 7 - rank
        return file, rank

    def focusWindow(self):
        self.setFocus()
        self.setWindowState(window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()

    def performMove(self, uci):
        def _updateMoveOnboard(move):
            self.chessboard.push(move)
            self.lastMove = move
            if self.chessboard.is_check():
                self.check = self.chessboard.king(self.chessboard.turn)
            else:
                self.check = None
            self.update()
            if self.chessboard.is_checkmate():
                logging.info("Checkmate")
                if self.chessboard.turn:
                    text = "Checkmate! Black wins!"
                else:
                    text = "Checkmate! White wins!"
                self.popup = QLabel(text)
                self.popup.setGeometry(self.geometry())
                self.popup.show()
            self.focusWindow()
            return True

        move = chess.Move.from_uci(uci)
        if self.chessboard.is_legal(move):
            return _updateMoveOnboard(move)
        else:
            move = chess.Move.from_uci(uci + 'q')
            if self.chessboard.is_legal(move):
                return _updateMoveOnboard(move)
            else:
                logging.error("Move not legal")
                self.lastMove = chess.Move.from_uci(self.lastReceived)
        return False

    @pyqtSlot(QWidget)
    def mousePressEvent(self, event):
        logging.debug(event)
        if self.isMyMove and self.svgX < event.x() <= self.svgX + self.cbSize and self.svgY < event.y() <= self.svgY + self.cbSize:  # mouse on chessboard
            if event.buttons() == Qt.LeftButton:
                # if the click is on chessBoard only
                if self.svgX + self.margin < event.x() < self.svgX + self.cbSize - self.margin and self.svgY + self.margin < event.y() < self.svgY + self.cbSize - self.margin:
                    file, rank = self.getPostFromCoordinates(event.x(), event.y())
                    square = chess.square(file, rank)  # chess.sqare.mirror() if white is on top
                    piece = self.chessboard.piece_at(square)
                    coordinates = '{}{}'.format(chr(file + 97), str(rank + 1))
                    if self.pieceToMove[0] is not None:
                        uci = '{}{}'.format(self.pieceToMove[1], coordinates)
                        logging.info("Got event %s" % uci)
                        if self.performMove(uci):
                            self.isMyMove = False
                            self.appSocket.send(uci)
                            logging.info("Sent %s" % uci)
                        # print(self.chessboard.fen())
                        piece = None
                        coordinates = None
                    else:
                        self.lastMove = chess.Move.from_uci('{}{}'.format(coordinates, coordinates))
                    self.pieceToMove = [piece, coordinates]
                    logging.info("Selected: %s" % piece)
                else:
                    logging.info('coordinates clicked')
        else:
            QWidget.mousePressEvent(self, event)

    @pyqtSlot(QWidget)
    def paintEvent(self, event):
        self.chessboardSvg = chess.svg.board(self.chessboard, size=self.cbSize, coordinates=self.coordinates,
                                             lastmove=self.lastMove, flipped=self.flipped, check=self.check).encode(
            "UTF-8")
        self.widgetSvg.load(bytearray(self.chessboardSvg))

    @pyqtSlot(QSvgWidget)
    def resizeEvent(self, QResizeEvent):
        logging.info(self.geometry())
        rect = self.geometry()
        self.resizeWindow(rect.x(), rect.y(), rect.width(), rect.height())


if __name__ == "__main__":
    setBasicConfig()
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", dest='ip', help="Ip address of server", required=False)
    parser.add_argument("--port", dest='port', type=int, default=5000, help="Ip address of server", required=False)
    parser.add_argument("--size", dest='size', type=int, default=600, help="Size of board", required=False)
    parser.add_argument("--c960", dest='c960', action='store_true', help="Pass this for 960 game")
    args, _ = parser.parse_known_args()
    tdarkChess = QApplication([])
    window = MainWindow(args.c960, args.ip, args.port, size=args.size)
    window.show()
    tdarkChess.exec_()
