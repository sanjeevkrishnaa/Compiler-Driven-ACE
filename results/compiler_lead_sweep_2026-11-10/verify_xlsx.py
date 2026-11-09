"""Independently check exported values, errors, chart bindings and panes."""
import json,math,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'evidence.json').read_text())
target=ROOT.parents[1]/'outputs/01a1a8b4-eb78-7a00-9b8b-8e0b77555f04/QAOA_generation_lead_sweep.xlsx'
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    book=ET.fromstring(z.read('xl/workbook.xml'))
    assert [s.attrib['name'] for s in book.findall('s:sheets/s:sheet',ns)]==['Sweep','Runs','Evidence']
    sheets=[ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')) for i in (1,2,3)]
    for sheet in sheets:
        assert not [c for c in sheet.findall('.//s:c',ns) if c.attrib.get('t')=='e']
        assert sheet.find('s:sheetViews/s:sheetView',ns).attrib.get('showGridLines') in ('0','false')
    cells={c.attrib['r']:c for c in sheets[0].findall('.//s:c',ns)}
    def number(address):
        return float(cells[address].find('s:v',ns).text)
    assert number('C6')==data['winner']['lead']
    assert math.isclose(number('G6'),data['winner']['mean_latency_ms'],abs_tol=1e-10)
    for a in data['aggregate']:
        r=a['lead']+12
        for col,key in [('E','mean_latency_ms'),('F','mean_completion_s'),('G','delivered_fidelity'),('I','waste'),('J','coverage')]:
            assert math.isclose(number(f'{col}{r}'),a[key],abs_tol=1e-10),(col,r)
    for sheet,cols in [(sheets[1],3),(sheets[2],1)]:
        pane=sheet.find('s:sheetViews/s:sheetView/s:pane',ns)
        assert float(pane.attrib.get('ySplit',0))==1
        assert float(pane.attrib.get('xSplit',0))==cols
    content_types=ET.fromstring(z.read('[Content_Types].xml'))
    charts=[part.attrib['PartName'].lstrip('/') for part in content_types
            if part.attrib.get('ContentType','').endswith('drawingml.chart+xml')]
    assert len(charts)==3
    for name in charts:
        chart=ET.fromstring(z.read(name))
        formulae=[f.text for f in chart.findall('.//c:f',ns)]
        assert any('$Q$13:$Q$21' in f for f in formulae),formulae
        colors={c.attrib['val'].upper() for c in chart.findall('.//a:srgbClr',ns)}
        assert {'2563EB','D97706'}<=colors,colors
print(json.dumps(dict(file=str(target),size=target.stat().st_size,winner=data['winner'],checks='cached results, no errors, three native charts, series bindings/colors, frozen panes, ZIP integrity verified'),indent=2))
