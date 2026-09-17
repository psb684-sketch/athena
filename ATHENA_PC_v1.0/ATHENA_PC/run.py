"""Double-click start.cmd on Windows, or run python3 run.py elsewhere."""
import sys
if sys.version_info < (3,10):
    print('ATHENA requires Python 3.10 or newer.')
    input('Press Enter to close. ')
    sys.exit(1)

import argparse
import json
import logging
import os
from pathlib import Path
import socket
import webbrowser
from athena.server import Application, Server

def data_directory(demo=False):
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local')) if sys.platform=='win32' else Path.home()/'.local'/'share'
    return base/('ATHENA-PC-Demo' if demo else 'ATHENA-PC')

def acquire_lock(path):
    handle=open(path,'a+b')
    handle.seek(0,2)
    if handle.tell()==0:
        handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if sys.platform=='win32':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None

def main():
    parser=argparse.ArgumentParser(description='ATHENA PC offline ERP')
    parser.add_argument('--demo',action='store_true',help='Use a separate, fictional demonstration database')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    directory=(args.data_dir or data_directory(args.demo)).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    lock=acquire_lock(directory/'running.lock')
    instance=directory/'instance.json'
    if lock is None:
        try:
            info=json.loads(instance.read_text(encoding='utf-8'))
            if not args.no_browser: webbrowser.open(info['url'])
            print('아테나가 이미 실행 중입니다. 기존 화면을 열었습니다.')
            return
        except (OSError,ValueError,KeyError):
            print('아테나가 실행 중입니다. 잠시 뒤 실행 파일을 다시 눌러 주세요.')
            return
    logging.basicConfig(filename=directory/'athena-error.log',level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    server=None
    try:
        app=Application(directory/'athena.db',Path(__file__).resolve().parent/'ui',args.demo)
        if args.demo:
            from athena.demo import seed
            seed(app.path)
            app.auto_backup()
        server=Server(app,args.port)
        url=f'{server.origin}/launch?token={app.token}'
        instance.write_text(json.dumps({'url':url,'pid':os.getpid(),'origin':server.origin}),encoding='utf-8')
        if sys.platform!='win32': instance.chmod(0o600)
        print('\n  ATHENA · 아테나 PC 1.0\n')
        print('  '+('체험용 가상 자료입니다. 실제 장부와 분리됩니다.' if args.demo else '업무 기록은 이 PC에 자동으로 저장됩니다.'))
        print(f'  데이터 위치: {directory}')
        print('  종료하려면 이 창에서 Ctrl+C를 누르세요.\n')
        if not args.no_browser: webbrowser.open(url)
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print('\n아테나를 종료합니다. 저장한 기록은 보존됩니다.')
    finally:
        if server: server.server_close()
        instance.unlink(missing_ok=True)
        lock.close()

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        logging.exception('Startup failed')
        print(f'실행하지 못했습니다: {exc}')
        sys.exit(1)
