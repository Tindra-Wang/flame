"""Execute one versioned detector experiment inside the existing GPU engine."""
from pathlib import Path
from .io import read_json,write_json,sha256
from .evaluation_data import prepare_detector_pair,validate_pair_report
from .evaluation import paired_yolo_experiment


def run(root,model_root=Path('/app/models')):
    request=read_json(root/'learning-request.json')
    for name in ('real','synthetic'):
        if sha256(root/f'inputs/{name}/version.json')!=request[f'{name}_version_sha256']:raise ValueError('训练版本与提交记录不一致')
    weights=Path(model_root)/request['weights']
    if sha256(weights)!=request['weights_sha256']:raise ValueError('训练初始权重在提交后改变')
    _,lineage=prepare_detector_pair(root/'inputs/real',root/'inputs/synthetic',root/'prepared',weights,request['parameters'])
    report=paired_yolo_experiment(root/'prepared/spec.json',root/'results')
    report.update(lineage=lineage,evidence_source='platform_paired_training',real_version=request['real_version'],synthetic_version=request['synthetic_version'])
    report['delta_pp']=validate_pair_report(report)
    write_json(root/'comparison.json',report);return report
