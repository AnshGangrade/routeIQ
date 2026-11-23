"""One request per isolated interpreter process; JSON only, no pickle or exec."""
import json
import math
import os
from pathlib import Path
import sys

# -I -S deliberately excludes project/site packages. Import only our trusted
# scoring interpreter, without importing the engine package or its dependencies.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from language import Interpreter


def install_limits(seconds):
    memory = 128 * 1024 * 1024
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', w.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.GetCurrentProcess.restype = w.HANDLE
        job = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | KILL_ON_JOB_CLOSE
        limits.basic.flags = 0x2 | 0x8 | 0x100 | 0x2000
        limits.basic.process_time = math.ceil(seconds) * 10_000_000
        limits.basic.active = 1
        limits.process_memory = memory
        if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise RuntimeError('Cannot install Windows job resource limits')
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise RuntimeError('Cannot enter limited Windows job')
        # Keep this handle until process exit (closing it kills this worker).
        return job, 'windows-job: cpu, memory, one process'
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(seconds), math.ceil(seconds)))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return None, 'posix-rlimit: cpu, memory, file size, core'
    raise RuntimeError('Resource isolation unsupported; refusing candidate execution')


def main():
    limits = None
    try:
        # Limits are installed BEFORE receiving/parsing candidate input.
        handle, limits = install_limits(float(sys.argv[1]))
        payload = sys.stdin.buffer.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError('Candidate input exceeds limit')
        data = json.loads(payload)
        output = Interpreter().run(data['source'], data['name'], data['context'])
        scores = output.get('scores') if isinstance(output, dict) else None
        if not isinstance(output, dict):
            raise TypeError('Invalid output type: expected a scores dictionary')
        if not isinstance(scores, dict) or set(scores) != set(data['context']['candidate_stops']):
            raise TypeError('Score count mismatch')
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in scores.values()):
            raise TypeError('Score is not finite or numeric (NaN/infinity rejected)')
        response = {'status': 'success', 'output': {'scores': scores}}
    except TimeoutError as exc:
        response = {'status': 'timeout', 'error': str(exc)}
    except TypeError as exc:
        response = {'status': 'invalid_output', 'error': str(exc)}
    except Exception as exc:
        response = {'status': 'runtime_error', 'error': f'{type(exc).__name__}: {exc}'}
    response['details'] = {'resource_limits': limits, 'pid': os.getpid()}
    sys.stdout.write(json.dumps(response, allow_nan=False))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
