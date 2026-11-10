"""Linux-local background execution. The CLI owns the EDA process and its audit."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent


def default_environment():
    verdi = os.environ.get('VERDI_HOME', '')
    executable = shutil.which('verdi')
    if not verdi and executable:
        verdi = str(Path(executable).resolve().parent.parent)
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return dict(verdi_home=verdi, license='',
                results_dir=os.environ.get('RTLWIRE_RESULTS_DIR', str(data / 'rtlwire/runs')))


def validate_environment(config):
    if sys.platform != 'linux':
        raise ValueError('RTLWire Studio 仅在 Linux 本机运行。')
    home = Path(config.get('verdi_home', '')).expanduser()
    if not config.get('verdi_home') or not (home / 'bin/verdi').is_file():
        raise ValueError('未找到本机 Verdi。请加载 EDA 环境，或在“运行环境”选择 Verdi 安装目录。')
    if not config.get('results_dir'):
        raise ValueError('请设置检查结果保存目录。')


class AnalysisJob:
    cli_module = 'rtlwire'
    def __init__(self, config, environment, events):
        validate_environment(environment)
        self.config, self.environment, self.events = config, dict(environment), events
        self.id = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
        self.directory = Path(environment['results_dir']).expanduser().absolute() / self.id
        self.cancel_requested = threading.Event()
        self.thread = None

    def emit(self, event, **fields):
        self.events.put(dict(event=event, job=self.id, **fields))

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=False)
        self.thread = threading.Thread(target=self._run, name='rtlwire-' + self.id, daemon=True)
        self.thread.start()
        return self

    def cancel(self):
        if not self.cancel_requested.is_set():
            self.cancel_requested.set()
            (self.directory / 'cancel').write_text('cancel')
            self.emit('log', message='已请求取消，正在结束本次提取并保留审计。')

    def _run(self):
        try:
            (self.directory / 'query.json').write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
            result = self.directory / 'result'
            env = os.environ.copy()
            env['VERDI_HOME'] = str(Path(self.environment['verdi_home']).expanduser())
            env['PYTHONIOENCODING'] = 'utf-8'
            if self.environment.get('license'):
                env['LM_LICENSE_FILE'] = env['SNPSLMD_LICENSE_FILE'] = self.environment['license']
            command = [sys.executable, '-m', self.cli_module, '--query', str(self.directory / 'query.json'),
                       '--out', str(result), '--cancel-file', str(self.directory / 'cancel'), '--progress-json']
            if self.cancel_requested.is_set():
                self.emit('done', status='cancelled', directory='', returncode=130)
                return
            process = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='replace', bufsize=1)
            for line in process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if item.get('event') == 'phase':
                        self.emit('phase', phase=item['phase'], message=item['message'])
                    else:
                        self.emit('log', message=line)
                except (ValueError, AttributeError):
                    self.emit('log', message=line)
            rc = process.wait()
            status = 'cancelled' if self.cancel_requested.is_set() else 'complete' if rc == 0 else 'partial' if rc == 3 else 'failed'
            self.emit('done', status=status, directory=str(result), returncode=rc)
        except Exception as exc:
            self.emit('error', message=str(exc), directory=str(self.directory))


class WaveAnalysisJob(AnalysisJob):
    cli_module = 'rtlwire.wave_cli'


def load_result(directory):
    directory = Path(directory)
    data = {}
    for name in ('graph', 'report', 'paths', 'audit', 'manifest', 'query', 'summary'):
        path = directory / (name + '.json')
        data[name] = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    if not data['graph']:
        raise ValueError('该目录没有 graph.json。请选择一次已经完成数据提取的结果目录。')
    data['directory'] = str(directory.absolute())
    return data
