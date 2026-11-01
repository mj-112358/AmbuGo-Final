"""Repair dangling predecessor references at verified unconnected source boundaries.

The repair targets invalid boundary references and preserves lane geometry,
road shape, connections and valid road/junction references. Inspect the
resulting network during native Vissim import."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET


def repair(network, candidate, output, report):
    source = ET.parse(network).getroot()
    edges = {e.get('id'): e for e in source.findall('edge')}
    nodes = {j.get('id'): j for j in source.findall('junction')}
    connections = source.findall('connection')
    text = Path(candidate).read_text()
    tree = ET.fromstring(text)
    junctions = {j.get('id') for j in tree.findall('junction')}
    changes = []
    for road in tree.findall('road'):
        for link in road.findall('link/*'):
            if link.get('elementType') != 'junction' or link.get('elementId') in junctions:
                continue
            sid = next(u.get('value') for u in road.findall('userData') if u.get('code') == 'sumoId')
            edge = edges[sid]
            node = nodes[edge.get('from')]
            assert link.tag == 'predecessor', 'Unresolved non-boundary reference needs manual review.'
            assert node.get('type') == 'dead_end' and not node.get('intLanes')
            assert not any(c.get('to') == sid for c in connections)
            changes.append({'road': road.get('id'), 'source_edge': sid,
                            'removed_predecessor_junction': link.get('elementId'),
                            'source_boundary_node': node.get('id'),
                            'source_incoming_connections': 0})
            # Preserve the original OpenDRIVE text, projection CDATA and all
            # geometry numbers; delete just this verified invalid reference.
            pattern = r'(<road\b[^>]*\bid="' + re.escape(road.get('id')) + r'"[^>]*>)(.*?)(</road>)'
            match = re.search(pattern, text, flags=re.S)
            assert match
            body = match.group(2)
            replacement, count = re.subn(
                r'\s*<predecessor\s+elementType="junction"\s+elementId="' +
                re.escape(link.get('elementId')) + r'"\s*/>', '', body)
            assert count == 1
            text = text[:match.start(2)] + replacement + text[match.end(2):]
    result = ET.fromstring(text)
    road_ids = {r.get('id') for r in result.findall('road')}
    for link in result.findall('road/link/*'):
        assert link.get('elementId') in (junctions if link.get('elementType') == 'junction' else road_ids)
    for before, after in zip(tree.findall('road'), result.findall('road')):
        for tag in ('planView', 'lanes', 'elevationProfile', 'lateralProfile'):
            a, b = before.find(tag), after.find(tag)
            assert (None if a is None else ET.tostring(a)) == (None if b is None else ET.tostring(b))
    Path(output).write_text(text)
    Path(report).write_text(json.dumps({'changes': changes, 'remaining_missing_references': 0,
        'geometry_and_lane_elements_unchanged': True, 'native_vissim_tested': False,
        'output_sha256': hashlib.sha256(Path(output).read_bytes()).hexdigest()}, indent=2))
    return changes


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_sumo_network', type=Path)
    p.add_argument('input_xodr', type=Path)
    p.add_argument('output_xodr', type=Path)
    p.add_argument('report_json', type=Path)
    a = p.parse_args()
    print(json.dumps(repair(a.source_sumo_network, a.input_xodr, a.output_xodr, a.report_json), indent=2))
