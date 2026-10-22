import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
result=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
(root/'docs'/'test-output.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
print(result.stdout)
if result.returncode:raise SystemExit(result.returncode)
for command in [['node','--check','static/app.js'],['node','--check','static/maps.js'],['node','--check','static/location-picker.js'],['node','--check','static/place-photos.js'],['node','--check','static/wikimedia-photos.js'],[sys.executable,'-m','pip','check']]:
    subprocess.run(command,cwd=root,check=True)
