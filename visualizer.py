import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel
from PyQt5.QtCore import QTimer
from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudioFormat, QAudioInput
import numpy as np
import pyqtgraph as pg

class AudioVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.initUI()
        self.initAudio()

    def initUI(self):
        self.setWindowTitle('Arduino Synth Visualizer')
        self.setGeometry(100, 100, 800, 600)

        # Main layout
        centralWidget = QWidget(self)
        self.setCentralWidget(centralWidget)
        layout = QVBoxLayout(centralWidget)

        # Visualization
        self.plotWidget = pg.PlotWidget(self)
        layout.addWidget(self.plotWidget)

        # Control buttons
        self.connectButton = QPushButton('Connect to Arduino', self)
        layout.addWidget(self.connectButton)

        self.visualizeButton = QPushButton('Visualize', self)
        layout.addWidget(self.visualizeButton)

        # Label
        self.statusLabel = QLabel("Status: Disconnected", self)
        layout.addWidget(self.statusLabel)

    def initAudio(self):
        self.audioInput = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updatePlot)

        self.audioStream = None

    def startAudio(self):
        format = QAudioFormat()
        format.setChannelCount(1)
        format.setSampleRate(44100)
        format.setSampleSize(16)
        format.setCodec("audio/pcm")
        format.setByteOrder(QAudioFormat.LittleEndian)
        format.setSampleType(QAudioFormat.SignedInt)

        info = QAudioDeviceInfo(QAudioDeviceInfo.defaultInputDevice())
        if not info.isFormatSupported(format):
            print("Default format not supported, trying to use the nearest")
            format = info.nearestFormat(format)

        self.audioInput = QAudioInput(format, self)
        self.audioStream = self.audioInput.start()
        self.timer.start(50)

    def updatePlot(self):
        if self.audioStream is not None:
            data = self.audioStream.readAll()
            if data:
                samples = np.frombuffer(data, dtype=np.int16)
                self.plotWidget.plot(samples, clear=True)

app = QApplication(sys.argv)
visualizer = AudioVisualizer()
visualizer.show()
sys.exit(app.exec_())
