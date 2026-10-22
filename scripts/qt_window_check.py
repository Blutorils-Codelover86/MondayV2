"""Real QML/Qt input checks. Optional test-ui dependency; no desktop or personal state used."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from monday.config import Config
from monday.pet import PetHTTP, PetService


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('scenario',choices=['layout','input','expressions'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    app=QGuiApplication(['monday-ui-check'])
    with tempfile.TemporaryDirectory(prefix='monday-qt-') as folder:
        base=Path(folder);workspace=base/'workspace';workspace.mkdir()
        service=PetService(Config(roots=(workspace,),data_dir=base/'state',ollama_model='',laya_path=''))
        server=PetHTTP(service,'owned-qt-test')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        engine=QQmlApplicationEngine()
        engine.setInitialProperties({'endpoint':f'http://127.0.0.1:{server.server_port}','secret':'owned-qt-test'})
        engine.load(str(Path(__file__).resolve().parents[1]/'monday/ui/Pet.qml'))
        assert engine.rootObjects(),'QML did not load'
        window=engine.rootObjects()[0]
        def pump(ms=100):
            # Yield the GIL to the owned Python HTTP bridge as well as pumping Qt events.
            until=time.monotonic()+ms/1000
            while time.monotonic()<until:
                app.processEvents();time.sleep(.005)
        def wait(predicate,seconds=5):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                if predicate():return
                pump(30)
            raise AssertionError('Qt state did not reach expected value: '+str(service.snapshot()))
        def item(name):
            value=window.findChild(QObject,name)
            assert value is not None,name
            return value
        def click(value):
            point=value.mapToScene(QPointF(value.width()/2,value.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point)
            pump()
        def submit(text):
            wait(lambda:not window.property('busy'))
            click(item('commandInput'));item('commandInput').setProperty('text',text)
            QTest.keyClick(window,Qt.Key_Return)
            pump()
        def capture(name):
            if args.output:
                args.output.mkdir(parents=True,exist_ok=True)
                assert window.grabWindow().save(str(args.output/(name+'.png')))
        try:
            wait(lambda:service.ui_ready)
            pump(250)
            if args.scenario=='layout':
                assert window.width()==400
                desired=(window.property('requestedWidth'),window.property('requestedHeight'))
                assert window.minimumWidth()==window.maximumWidth()==desired[0]
                assert window.minimumHeight()==window.maximumHeight()==desired[1]
                # A compositor-assigned tile must never become the geometry request.
                window.resize(917,1020);pump(250)
                assert (window.property('requestedWidth'),window.property('requestedHeight'))==desired
                wait(lambda:service.ui_geometry==desired)
                click(item('collapseButton'))
                wait(lambda:not window.property('expanded'))
                assert window.property('requestedWidth')==116 and window.property('requestedHeight')==104
                click(item('petMouse'));wait(lambda:window.property('expanded'))
                assert window.property('requestedWidth')==400
                # Full, selectable result text survives rather than being elided after five lines.
                item('pollTimer').setProperty('running',False)
                text='A verified result with many lines. '*100
                window.setProperty('state',{'phase':'done','status':'PARTIAL','response':text})
                pump(200)
                assert item('responseText').property('text')==text
                assert window.property('requestedHeight')<650
                capture('window')
            elif args.scenario=='input':
                click(item('commandInput'))
                assert item('commandInput').property('activeFocus')
                QTest.keyClick(window,Qt.Key_H);QTest.keyClick(window,Qt.Key_I);QTest.keyClick(window,Qt.Key_Return)
                wait(lambda:bool(service.history))
                wait(lambda:'MONDAY' in item('responseText').property('text'))
                assert service.history[-1]['objective']=='hi'
                for decision,button in [('denied','denyButton'),('approved','approveButton'),('cancelled','sendButton')]:
                    target=workspace/decision
                    submit('tool fs.create '+json.dumps({'path':str(target),'content':'owned fixture'}))
                    wait(lambda:service.phase=='approval')
                    wait(lambda:window.property('expression')=='approval')
                    wait(lambda:item(button).isVisible())
                    assert window.property('expression')=='approval'
                    assert not item('collapseButton').property('enabled')
                    click(item(button))
                    wait(lambda:service.phase in ('done','error'))
                    wait(lambda:not window.property('busy'))
                    assert target.exists()==(decision=='approved')
                capture('result')
            else:
                item('pollTimer').setProperty('running',False)
                moods={
                    'idle':{'phase':'idle','status':'IDLE'},
                    'thinking':{'phase':'busy','status':'RUNNING'},
                    'success':{'phase':'done','status':'SUCCESS'},
                    'approval':{'phase':'approval','status':'RUNNING','approval':{'id':'test','prompt':'Approve the owned fixture?'}},
                    'warning':{'phase':'done','status':'PARTIAL'},
                    'error':{'phase':'error','status':'FAILED'},
                }
                window.contentItem().forceActiveFocus()
                QTest.mouseMove(window,QPoint(1,1))
                for mood,state in moods.items():
                    state.update(response='MONDAY — '+mood,progress='Reading verified observations…')
                    window.setProperty('state',state)
                    window.setProperty('celebrating',mood=='success')
                    pump(300)
                    assert item('petFace').property('mood')==mood,(mood,item('petFace').property('mood'))
                    capture(mood)
                window.setProperty('state',{'phase':'idle','status':'IDLE'})
                window.setProperty('celebrating',False)
                click(item('commandInput'));assert item('petFace').property('mood')=='listening'
                capture('listening')
                pump(350)
                window.setProperty('connected',False);pump()
                assert item('petFace').property('mood')=='offline'
                capture('offline')
            print('QT_WINDOW_CHECK_OK:',args.scenario)
        finally:
            window.close();service.shutdown();server.shutdown();server.server_close()
            if service.work_thread:service.work_thread.join(timeout=3)

if __name__=='__main__':main()
