from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
svg='''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="60" fill="#246b53"/><g stroke="#f4faf5" stroke-width="16" stroke-linecap="round"><path d="M64 110v36M96 82v92M128 58v140M160 94v68M192 112v32"/></g><circle cx="194" cy="60" r="10" fill="#acd2ba"/></svg>'''
(ROOT/'assets/app.svg').write_text(svg,encoding='utf-8')
app=QApplication([]); image=QImage(512,512,QImage.Format_ARGB32); image.fill(Qt.transparent)
painter=QPainter(image); QSvgRenderer(svg.encode()).render(painter); painter.end(); image.save(str(ROOT/'assets/app.png'))
Image.open(ROOT/'assets/app.png').save(ROOT/'assets/app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
