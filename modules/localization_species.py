"""Fenced species convergence. Inference is performed by the existing GPU runner."""
import json
import math

from modules.localization_active import StaleLease
from modules.localization_authority_store import AuthorityStore, fingerprint

CPU_ACTIONS=('cleanup','preserve','out_of_scope')
GPU_ACTIONS=('classify','fallback')
SPACE_TABLES={512:'image_embeddings_512',768:'image_embeddings_768',1280:'image_embeddings'}


class SpeciesStore:
    def __init__(self,connector=None):
        self.conn=connector if connector is not None else AuthorityStore().conn

    @staticmethod
    def semantic(tx,image_id):
        row=tx.query_one('SELECT localization_species_input(?) AS state',(image_id,))
        return row['state'] if row else None

    @staticmethod
    def _observe_source(tx,image_id,source):
        if source is None:
            return
        blank={k:{} for k in ('authority','discovery','ownership','reservation')}
        blank['source']=source
        tx.execute(
            'INSERT INTO localization_authority_observations (image_id,components) VALUES (?,?::jsonb) '
            'ON CONFLICT (image_id) DO NOTHING',(image_id,json.dumps(blank)),
        )
        tx.execute(
            "UPDATE localization_authority_observations SET components=jsonb_set(components,'{source}',?::jsonb),"
            'revision=revision+1,source_revision=source_revision+1,updated_at=clock_timestamp() '
            "WHERE image_id=? AND components->'source' IS DISTINCT FROM ?::jsonb",
            (json.dumps(source),image_id,json.dumps(source)),
        )

    def observe(self,image_id,*,source_observation=None):
        def observe(tx):
            ctl=tx.query_one('SELECT * FROM localization_authority_control WHERE id=1 FOR SHARE')
            if not ctl or ctl['mode']!='active':
                return None
            if not tx.query_one('SELECT id FROM images WHERE id=? FOR UPDATE',(image_id,)):
                return None
            self._observe_source(tx,image_id,source_observation)
            state=self.semantic(tx,image_id)
            if not state['in_scope'] and not state['managed']:
                return None
            tx.execute(
                'INSERT INTO localization_discovery_state (image_id,legacy_positive,selection_only,species_managed) '
                'VALUES (?,?,?,TRUE) ON CONFLICT (image_id) DO UPDATE SET species_managed=TRUE',
                (image_id,state['independent_discovery'],not state['independent_discovery']),
            )
            state=self.semantic(tx,image_id)
            current=tx.query_one(
                "SELECT * FROM localization_species_work WHERE image_id=? AND status='completed' "
                "AND disposition<>'superseded' AND input_state->'semantic'=?::jsonb ORDER BY id DESC LIMIT 1",
                (image_id,json.dumps(state)),
            )
            if current:
                return current
            action=('out_of_scope' if not state['in_scope'] else 'preserve' if state['curated_species'] else
                    'cleanup' if state['source'].get('status')!='available' else 'classify' if state['selection'] else 'fallback')
            captured={'semantic':state,'control_revision':ctl['revision']}
            key=fingerprint(captured)
            tx.execute(
                'INSERT INTO localization_species_work (image_id,input_fingerprint,input_state,action) '
                'VALUES (?,?,?::jsonb,?) ON CONFLICT DO NOTHING',(image_id,key,json.dumps(captured),action),
            )
            return tx.query_one('SELECT * FROM localization_species_work WHERE image_id=? AND input_fingerprint=?',(image_id,key))
        return self.conn.run_transaction(observe)

    def claim_next(self,*,image_id=None,actions=CPU_ACTIONS+GPU_ACTIONS):
        if not actions or not set(actions)<=set(CPU_ACTIONS+GPU_ACTIONS):
            raise ValueError('invalid species actions')
        def claim(tx):
            tx.execute(
                "UPDATE localization_species_work SET status='completed',disposition='retry_exhausted',"
                "completed_at=clock_timestamp(),lease_until=NULL WHERE status='running' "
                'AND lease_until<=clock_timestamp() AND attempts>=3',
            )
            condition=' AND image_id=?' if image_id is not None else ''
            params=tuple(actions)+((image_id,) if image_id is not None else ())
            return tx.query_one(
                'WITH picked AS (SELECT id FROM localization_species_work WHERE action IN ('+
                ','.join('?' for _ in actions)+')'+condition+
                " AND attempts<3 AND available_at<=clock_timestamp() AND (status='queued' OR "
                "(status='running' AND lease_until<=clock_timestamp())) "
                "AND EXISTS(SELECT 1 FROM localization_authority_control WHERE id=1 AND mode='active') "
                'ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) '
                "UPDATE localization_species_work w SET status='running',fencing_token=w.fencing_token+1,"
                "attempts=w.attempts+1,lease_until=clock_timestamp()+interval '60 seconds' "
                'FROM picked WHERE w.id=picked.id RETURNING w.*',params,
            )
        return self.conn.run_transaction(claim)

    def renew(self,claim):
        return bool(self.conn.execute(
            "UPDATE localization_species_work SET lease_until=clock_timestamp()+interval '60 seconds' "
            "WHERE id=? AND fencing_token=? AND status='running' AND lease_until>clock_timestamp()",
            (claim['id'],claim['fencing_token']),
        ))

    def scan_batch(self,limit=100):
        """Finite image watermark includes cleanup candidates outside species scope."""
        def scan(tx):
            ctl=tx.query_one('SELECT * FROM localization_authority_control WHERE id=1 FOR UPDATE')
            if ctl['mode']!='active':
                return []
            upper=ctl['species_scan_upper_bound'] or tx.query_one('SELECT COALESCE(MAX(id),0) AS id FROM images')['id']
            tx.execute('UPDATE localization_authority_control SET species_scan_upper_bound=? WHERE id=1',(upper,))
            rows=tx.query(
                'SELECT i.id,i.file_path FROM images i WHERE i.id>? AND i.id<=? AND ('
                'EXISTS(SELECT 1 FROM localization_discovery_evidence d WHERE d.image_id=i.id AND d.independent) OR '
                'EXISTS(SELECT 1 FROM localization_discovery_state d WHERE d.image_id=i.id AND d.species_managed) OR '
                'EXISTS(SELECT 1 FROM image_localization_selections s JOIN localization_selection_lineage l ON l.selection_id=s.id WHERE s.image_id=i.id)) '
                'ORDER BY i.id LIMIT ?',(ctl['species_scan_cursor'],upper,max(1,min(int(limit),100))),
            )
            if not rows:
                tx.execute('UPDATE localization_authority_control SET species_scan_cursor=0,species_scan_upper_bound=0 WHERE id=1')
            for row in rows:
                row.update(scan_revision=ctl['revision'],scan_cursor=ctl['species_scan_cursor'],scan_upper_bound=upper)
            return rows
        return self.conn.run_transaction(scan)

    def finish_scan(self,rows):
        if not rows:
            return
        last=rows[-1]
        self.conn.execute(
            'UPDATE localization_authority_control SET species_scan_cursor=? WHERE id=1 AND revision=? '
            'AND species_scan_cursor=? AND species_scan_upper_bound=?',
            (last['id'],last['scan_revision'],last['scan_cursor'],last['scan_upper_bound']),
        )

    def fail(self,claim,error):
        return bool(self.conn.execute(
            "UPDATE localization_species_work SET status=CASE WHEN attempts>=3 THEN 'completed' ELSE 'queued' END,"
            "disposition=CASE WHEN attempts>=3 THEN 'retry_exhausted' ELSE NULL END,last_error=?,lease_until=NULL,"
            "completed_at=CASE WHEN attempts>=3 THEN clock_timestamp() ELSE NULL END,"
            "available_at=clock_timestamp()+CASE WHEN attempts=1 THEN interval '60 seconds' ELSE interval '300 seconds' END "
            "WHERE id=? AND fencing_token=? AND status='running' AND lease_until>clock_timestamp()",
            (str(error)[:256],claim['id'],claim['fencing_token']),
        ))

    @staticmethod
    def _finish(tx,claim,disposition):
        if not tx.execute(
            "UPDATE localization_species_work SET status='completed',disposition=?,completed_at=clock_timestamp(),"
            "lease_until=NULL WHERE id=? AND fencing_token=? AND status='running' AND lease_until>clock_timestamp()",
            (disposition,claim['id'],claim['fencing_token']),
        ):
            raise StaleLease('species lease expired during publication')

    @staticmethod
    def _delete_owned(tx,image_id):
        rows=tx.query('SELECT * FROM localization_species_outputs WHERE image_id=? ORDER BY kind,resource_key FOR UPDATE',(image_id,))
        for row in rows:
            owned=tx.query_one('SELECT localization_species_owns(?,?,?) AS owned',(image_id,row['kind'],row['resource_key']))['owned']
            if not owned:
                continue
            if row['kind']=='keyword':
                tx.execute('DELETE FROM image_keywords WHERE image_id=? AND keyword_id=?',(image_id,int(row['resource_key'])))
            else:
                space=tx.query_one('SELECT dim FROM embedding_spaces WHERE id=?',(int(row['resource_key']),))
                if space and space['dim'] in SPACE_TABLES:
                    tx.execute('DELETE FROM '+SPACE_TABLES[space['dim']]+' WHERE image_id=? AND embedding_space_id=?',(image_id,int(row['resource_key'])))
            tx.execute('DELETE FROM localization_species_outputs WHERE image_id=? AND kind=? AND resource_key=?',
                       (image_id,row['kind'],row['resource_key']))

    @staticmethod
    def _lineage(tx,claim,kind,resource,value):
        event=tx.query_one(
            "SELECT MAX(id) AS id FROM localization_change_journal WHERE image_id=? AND resource_key=? "
            "AND (kind=? OR (?='keyword' AND kind='discovery'))",
            (claim['image_id'],str(resource),kind,kind),
        )['id']
        if event is None:
            raise RuntimeError('missing species publication journal')
        tx.execute(
            'INSERT INTO localization_species_outputs (image_id,kind,resource_key,work_id,produced_event_id,value_fingerprint) '
            'VALUES (?,?,?,?,?,?) ON CONFLICT (image_id,kind,resource_key) DO UPDATE SET work_id=EXCLUDED.work_id,'
            'produced_event_id=EXCLUDED.produced_event_id,value_fingerprint=EXCLUDED.value_fingerprint',
            (claim['image_id'],kind,str(resource),claim['id'],event,fingerprint(value)),
        )

    def _keyword(self,tx,claim,name,confidence,source):
        key=tx.query_one('SELECT keyword_id FROM keywords_dim WHERE keyword_norm=?',(name.lower(),))
        if not key:
            key=tx.query_one(
                'INSERT INTO keywords_dim (keyword_norm,keyword_display) VALUES (?,?) '
                'ON CONFLICT (keyword_norm) DO UPDATE SET keyword_norm=EXCLUDED.keyword_norm RETURNING keyword_id',
                (name.lower(),name),
            )
        kid=key['keyword_id']
        if tx.query_one('SELECT 1 AS present FROM image_keywords WHERE image_id=? AND keyword_id=?',(claim['image_id'],kid)):
            return  # Existing protected resource, including an independent birds tag.
        tx.execute('INSERT INTO image_keywords (image_id,keyword_id,source,confidence,relevance_weight) VALUES (?,?,?,?,1)',
                   (claim['image_id'],kid,source,confidence))
        self._lineage(tx,claim,'keyword',kid,{'name':name,'confidence':confidence,'source':source})

    def _embedding(self,tx,claim,embedding,space_code,model_version):
        if space_code not in ('bioclip_2_image','bioclip_2_crop'):
            raise ValueError('unsupported species embedding space')
        space=tx.query_one('SELECT id,dim FROM embedding_spaces WHERE code=?',(space_code,))
        if not space or space['dim'] not in SPACE_TABLES:
            raise ValueError('species embedding space unavailable')
        table=SPACE_TABLES[space['dim']]
        if tx.query_one('SELECT 1 AS present FROM '+table+' WHERE image_id=? AND embedding_space_id=?',(claim['image_id'],space['id'])):
            return False
        values=[float(v) for v in embedding]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('nonfinite species embedding')
        tx.execute('INSERT INTO '+table+' (image_id,embedding_space_id,embedding,model_version) VALUES (?,?,?::vector,?)',
                   (claim['image_id'],space['id'],json.dumps(values),model_version))
        self._lineage(tx,claim,'embedding',space['id'],values)
        return True

    def publish(self,claim,*,predictions=None,embedding=None,space_code='bioclip_2_crop',model_version='authority-species/1',source_observation=None):
        def publish(tx):
            ctl=tx.query_one('SELECT * FROM localization_authority_control WHERE id=1 FOR SHARE')
            selection=claim['input_state']['semantic'].get('selection') or {}
            if selection.get('policy_hash'):
                tx.query_one('SELECT policy_hash FROM localization_authority_policies WHERE policy_hash=? FOR SHARE',(selection['policy_hash'],))
                tx.query_one('SELECT policy_hash FROM localization_policy_approvals WHERE policy_hash=? FOR SHARE',(selection['policy_hash'],))
            tx.query_one('SELECT id FROM images WHERE id=? FOR UPDATE',(claim['image_id'],))
            current=tx.query_one('SELECT *,lease_until>clock_timestamp() AS live FROM localization_species_work WHERE id=? FOR UPDATE',(claim['id'],))
            if not current or current['status']!='running' or not current['live'] or current['fencing_token']!=claim['fencing_token']:
                return False
            state=self.semantic(tx,claim['image_id'])
            if (ctl['mode']!='active' or ctl['revision']!=current['input_state']['control_revision']
                    or state!=current['input_state']['semantic']
                    or (source_observation is not None and source_observation!=state['source'])):
                self._finish(tx,claim,'superseded')
                return False
            tx.execute("SELECT set_config('vexlum.authority_publication',?,TRUE)",(f"species:{claim['id']}",))
            self._delete_owned(tx,claim['image_id'])
            action=current['action']
            if action in GPU_ACTIONS:
                if embedding is None:
                    raise ValueError('species classification requires its embedding')
                for name,confidence in predictions or []:
                    if not isinstance(name,str) or not name.strip() or not math.isfinite(float(confidence)) or not 0<=float(confidence)<=1:
                        raise ValueError('invalid species prediction')
                    self._keyword(tx,claim,'species:'+name.strip(),float(confidence),'bioclip_region' if action=='classify' else 'bioclip')
                self._keyword(tx,claim,'birds',1.0,'localization_compat')
                embedded=self._embedding(tx,claim,embedding,space_code,model_version)
                disposition='classified' if predictions else 'no_species_match'
                if not embedded and predictions:
                    disposition='classified_embedding_preserved'
                status='done' if predictions else 'skipped'
                reason=None if predictions else 'no_species_match'
            else:
                disposition={'preserve':'preserved','cleanup':'source_unavailable','out_of_scope':'out_of_scope'}[action]
                status='done' if action=='preserve' else 'failed' if action=='cleanup' else 'skipped'
                reason=disposition
            phase=tx.query_one("SELECT id FROM pipeline_phases WHERE code='bird_species'")
            if not phase:
                raise RuntimeError('bird_species phase unavailable')
            tx.execute(
                'INSERT INTO image_phase_status (image_id,phase_id,status,skip_reason,executor_version,finished_at,updated_at) '
                "VALUES (?,?,?,?, 'authority-species/1',clock_timestamp(),clock_timestamp()) "
                'ON CONFLICT (image_id,phase_id) DO UPDATE SET status=EXCLUDED.status,skip_reason=EXCLUDED.skip_reason,'
                'executor_version=EXCLUDED.executor_version,finished_at=EXCLUDED.finished_at,updated_at=EXCLUDED.updated_at',
                (claim['image_id'],phase['id'],status,reason),
            )
            self._finish(tx,claim,disposition)
            return True
        try:
            return self.conn.run_transaction(publish)
        except StaleLease:
            return False
