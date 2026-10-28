"""Generate a tenant-scoped PostgreSQL design DDL; not a deployed migration."""
from pathlib import Path

OUT=Path(__file__).resolve().parents[2]/'docs/design'


def main():
    sql=['-- AI-07 target schema DESIGN ONLY; PostgreSQL. Review in migration before deployment.',
         '-- UUIDs are supplied by application; no paid extension or storage service required.',
         "CREATE TABLE user_account (id uuid PRIMARY KEY, email text NOT NULL UNIQUE, password_hash text NOT NULL, disabled boolean NOT NULL DEFAULT false);",
         "CREATE TABLE project (id uuid PRIMARY KEY, name text NOT NULL, owner_id uuid NOT NULL REFERENCES user_account(id), created_at timestamptz NOT NULL DEFAULT now());",
         "CREATE TABLE project_member (project_id uuid NOT NULL REFERENCES project(id), user_id uuid NOT NULL REFERENCES user_account(id), role text NOT NULL CHECK(role IN ('admin','builder','reviewer')), PRIMARY KEY(project_id,user_id));"]
    def table(name,fields,refs=(),checks=()):
        parts=['id uuid PRIMARY KEY','project_id uuid NOT NULL REFERENCES project(id)',*fields,'UNIQUE(project_id,id)']
        for col,target in refs: parts.append(f'FOREIGN KEY(project_id,{col}) REFERENCES {target}(project_id,id)')
        parts.extend(checks)
        sql.append(f'CREATE TABLE {name} (\n  '+',\n  '.join(parts)+'\n);')
    table('source_record',['uri text NOT NULL','license_id text NOT NULL','redistribution_allowed boolean NOT NULL DEFAULT false','pii_assessment jsonb NOT NULL','ethics_record_uri text','source_sha256 text'])
    table('model_asset',['source_id uuid NOT NULL','name text NOT NULL','revision text NOT NULL','sha256 text NOT NULL','storage_uri text NOT NULL'],[('source_id','source_record')])
    table('scene_config',['name text NOT NULL','config jsonb NOT NULL','config_sha256 text NOT NULL','revision integer NOT NULL','UNIQUE(project_id,name,revision)'])
    table('worker_node',['service_user_id uuid NOT NULL REFERENCES user_account(id)','capabilities jsonb NOT NULL','last_heartbeat timestamptz','disabled boolean NOT NULL DEFAULT false'])
    table('job',['scene_id uuid','model_id uuid','worker_id uuid','idempotency_key text NOT NULL','status text NOT NULL','config_snapshot jsonb NOT NULL','lease_generation integer NOT NULL DEFAULT 0','lease_until timestamptz','heartbeat_at timestamptz','cancel_requested boolean NOT NULL DEFAULT false','budget_limits jsonb NOT NULL','created_by uuid NOT NULL REFERENCES user_account(id)','created_at timestamptz NOT NULL DEFAULT now()'],[('scene_id','scene_config'),('model_id','model_asset'),('worker_id','worker_node')],["CHECK(status IN ('queued','running','retry_wait','succeeded','failed','cancel_requested','cancelled'))",'UNIQUE(project_id,idempotency_key)'])
    table('job_stage',['job_id uuid NOT NULL','name text NOT NULL','attempt integer NOT NULL CHECK(attempt>0)','status text NOT NULL','image_digest text NOT NULL','seed bigint','input_manifest_sha text NOT NULL','output_manifest_sha text','log_uri text','started_at timestamptz','finished_at timestamptz','error jsonb'],[('job_id','job')],['UNIQUE(project_id,job_id,name,attempt)'])
    table('artifact',['job_id uuid','kind text NOT NULL','sha256 text NOT NULL','storage_uri text NOT NULL','bytes bigint NOT NULL CHECK(bytes>=0)','created_at timestamptz NOT NULL DEFAULT now()'],[('job_id','job')])
    table('sample',['job_id uuid','source_id uuid NOT NULL','image_artifact_id uuid NOT NULL','mask_artifact_id uuid','parent_sample_id uuid','group_id text NOT NULL','source_kind text NOT NULL','width integer NOT NULL CHECK(width>0)','height integer NOT NULL CHECK(height>0)','metadata jsonb NOT NULL'],[('job_id','job'),('source_id','source_record'),('image_artifact_id','artifact'),('mask_artifact_id','artifact'),('parent_sample_id','sample')],["CHECK(source_kind IN ('real','fds_visual_proxy','visual_negative','diffusion','preview'))"])
    table('annotation_revision',['sample_id uuid NOT NULL','revision integer NOT NULL CHECK(revision>0)','origin text NOT NULL','image_sha256 text NOT NULL','labels_sha256 text NOT NULL','label_studio_annotation_id text','external_modified_at timestamptz','author_id uuid REFERENCES user_account(id)','created_at timestamptz NOT NULL DEFAULT now()'],[('sample_id','sample')],['UNIQUE(project_id,sample_id,revision)','UNIQUE(project_id,sample_id,id)'])
    table('label_box',['annotation_revision_id uuid NOT NULL','class_name text NOT NULL CHECK(class_name=\'fire\')','x0 double precision NOT NULL','y0 double precision NOT NULL','x1 double precision NOT NULL','y1 double precision NOT NULL'],[('annotation_revision_id','annotation_revision')],['CHECK(x0>=0 AND y0>=0 AND x1>x0 AND y1>y0)'])
    table('review_decision',['sample_id uuid NOT NULL','annotation_revision_id uuid NOT NULL','reviewer_id uuid NOT NULL REFERENCES user_account(id)','decision text NOT NULL CHECK(decision IN (\'approved\',\'rejected\'))','image_sha256 text NOT NULL','reason text','created_at timestamptz NOT NULL DEFAULT now()'],[('sample_id','sample'),('annotation_revision_id','annotation_revision')],['FOREIGN KEY(project_id,sample_id,annotation_revision_id) REFERENCES annotation_revision(project_id,sample_id,id)','UNIQUE(project_id,sample_id,annotation_revision_id,id)'])
    table('quality_result',['sample_id uuid NOT NULL','annotation_revision_id uuid','rule_version text NOT NULL','passed boolean NOT NULL','metrics jsonb NOT NULL','created_at timestamptz NOT NULL DEFAULT now()'],[('sample_id','sample'),('annotation_revision_id','annotation_revision')],['FOREIGN KEY(project_id,sample_id,annotation_revision_id) REFERENCES annotation_revision(project_id,sample_id,id)','UNIQUE(project_id,sample_id,annotation_revision_id,id)'])
    table('dataset_version',['version text NOT NULL','state text NOT NULL','manifest_sha256 text','dvc_commit text','code_commit text','parent_version_id uuid','release_error jsonb','created_at timestamptz NOT NULL DEFAULT now()'],[('parent_version_id','dataset_version')],["CHECK(state IN ('draft','dvc_pending','published','failed'))",'UNIQUE(project_id,version)'])
    table('version_sample',['version_id uuid NOT NULL','sample_id uuid NOT NULL','annotation_revision_id uuid NOT NULL','review_id uuid NOT NULL','quality_id uuid NOT NULL','split text NOT NULL CHECK(split IN (\'train\',\'val\',\'test\'))','group_id text NOT NULL','image_sha256 text NOT NULL','labels_sha256 text NOT NULL'],[('version_id','dataset_version'),('sample_id','sample')],['UNIQUE(project_id,version_id,sample_id)','FOREIGN KEY(project_id,sample_id,annotation_revision_id) REFERENCES annotation_revision(project_id,sample_id,id)','FOREIGN KEY(project_id,sample_id,annotation_revision_id,review_id) REFERENCES review_decision(project_id,sample_id,annotation_revision_id,id)','FOREIGN KEY(project_id,sample_id,annotation_revision_id,quality_id) REFERENCES quality_result(project_id,sample_id,annotation_revision_id,id)'])
    table('export_record',['version_id uuid NOT NULL','artifact_id uuid NOT NULL','format text NOT NULL CHECK(format IN (\'coco\',\'yolo\'))','manifest_sha256 text NOT NULL'],[('version_id','dataset_version'),('artifact_id','artifact')])
    table('experiment',['model_id uuid','kind text NOT NULL CHECK(kind IN (\'physical\',\'fid\',\'detection_pair\',\'visual_review\'))','config jsonb NOT NULL','reference_uri text','reference_sha256 text','status text NOT NULL'],[('model_id','model_asset')])
    table('experiment_arm',['experiment_id uuid NOT NULL','train_version_id uuid','val_version_id uuid','test_version_id uuid','name text NOT NULL','seed bigint','initial_weight_sha256 text','training_budget jsonb','actual_usage jsonb','UNIQUE(project_id,experiment_id,name)'],[('experiment_id','experiment'),('train_version_id','dataset_version'),('val_version_id','dataset_version'),('test_version_id','dataset_version')],['UNIQUE(project_id,experiment_id,id)'])
    table('metric_result',['experiment_id uuid NOT NULL','arm_id uuid','name text NOT NULL','value double precision','unit text NOT NULL','definition jsonb NOT NULL','evidence_artifact_id uuid'],[('experiment_id','experiment'),('arm_id','experiment_arm'),('evidence_artifact_id','artifact')],['FOREIGN KEY(project_id,experiment_id,arm_id) REFERENCES experiment_arm(project_id,experiment_id,id)'])
    table('budget_usage',['job_id uuid','kind text NOT NULL','quantity numeric NOT NULL CHECK(quantity>=0)','unit text NOT NULL','price_snapshot jsonb NOT NULL','amount_cny numeric NOT NULL CHECK(amount_cny>=0)','created_at timestamptz NOT NULL DEFAULT now()'],[('job_id','job')])
    table('audit_event',['actor_id uuid REFERENCES user_account(id)','action text NOT NULL','object_type text NOT NULL','object_id uuid','result jsonb NOT NULL','created_at timestamptz NOT NULL DEFAULT now()'])
    table('delivery_evidence',['artifact_id uuid NOT NULL','requirement_id text NOT NULL','status text NOT NULL','verified_by uuid REFERENCES user_account(id)','verified_at timestamptz'],[('artifact_id','artifact')])
    sql += ['CREATE INDEX job_claim_idx ON job(project_id,status,created_at);','CREATE INDEX sample_filter_idx ON sample(project_id,source_kind,group_id);','CREATE INDEX audit_time_idx ON audit_event(project_id,created_at);',
            '-- Required application/trigger invariants before deployment:',
            '-- 1. boxes within sample width/height; review SHA must match current immutable image.',
            '-- 2. version_sample requires approved review + passed quality + legal redistribution.',
            '-- 3. published version and referenced annotation/review snapshots cannot be edited.',
            '-- 4. one split per (version, group_id); detect parent/event leakage across datasets.',
            '-- 5. audit_event append-only under runtime database roles; uploads/downloads authorize project.',
            '-- 6. DVC success + independent backup verification precede published state.',
            '-- 7. project ownership and service_user membership are enforced by authorization service.',
            '-- 8. lease_generation fences delayed callbacks; never execute shell text from job config.']
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'schema.design.sql').write_text('\n\n'.join(sql)+'\n',encoding='utf-8')
    print(f'Wrote {sum(x.startswith("CREATE TABLE") for x in sql)} design tables')


if __name__=='__main__': main()
