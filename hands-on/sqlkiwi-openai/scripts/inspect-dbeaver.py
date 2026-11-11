"""Read installed artifacts; export derived facts, never DBeaver source code."""
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

root = Path(os.environ['LOCALAPPDATA']) / 'DBeaver'
project = Path(__file__).resolve().parents[1]
scratch = project.parents[1] / '.temp' / 'sqlkiwi-openai-dbeaver'
scratch.mkdir(parents=True, exist_ok=True)
facts = []
for prefix in ['core_', 'ui.editors.sql_', 'model.sql_', 'model_', 'ui.editors.data_',
               'ui.navigator_', 'ext.sqlite_', 'ext.postgresql_', 'ext.mysql_', 'registry_']:
    jar = next((root / 'plugins').glob('org.jkiss.dbeaver.' + prefix + '*.jar'))
    with ZipFile(jar) as archive:
        record = {'file': jar.name, 'sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
                  'entryCount': len(archive.infolist()), 'selectedClasses': []}
        for name in archive.namelist():
            if name.endswith(('/SQLQueryJob.class', '/SQLScriptParser.class', '/ModelPreferences.class')):
                payload = archive.read(name)
                record['selectedClasses'].append({'path': name, 'sha256': hashlib.sha256(payload).hexdigest()})
                (scratch / Path(name).name).write_bytes(payload)
        if prefix == 'ui.editors.sql_':
            xml = ET.fromstring(archive.read('plugin.xml'))
            record['keyBindings'] = [e.attrib for e in xml.iter('key')
                if e.get('commandId', '').endswith(('.run.statement', '.run.script', '.cancel.query'))]
            record['handlers'] = [e.attrib for e in xml.iter('handler')
                if e.get('commandId', '').endswith(('.run.statement', '.run.script', '.cancel.query'))]
        facts.append(record)
output = project / 'docs' / 'evidence' / 'installed-artifacts.json'
output.write_text(json.dumps({'scope': 'static installed JAR metadata, no runtime observation',
    'root': str(root), 'artifacts': facts}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'facts': str(output), 'selectedClassScratch': str(scratch), 'artifacts': len(facts)}))
