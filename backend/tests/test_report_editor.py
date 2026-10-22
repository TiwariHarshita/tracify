import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

TEST_URL=os.getenv("TRACE_AUTH_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("Set TRACE_AUTH_TEST_DATABASE_URL for isolated PostgreSQL checks",allow_module_level=True)
os.environ.setdefault("DATABASE_URL",TEST_URL)
os.environ.setdefault("SESSION_SECRET","phase-six-test-only-secret-012345678901234567")

from app.api.dependencies import get_current_user
from app.api.v1.routes.report_editor import router
from app.models.workspace import Report
from app.services import report_editor
from test_csv_api import env,upload

HEADERS={"X-Trace-Client":"web"}


def setup(env,data=b"amount,day\n1,Sun\n2,Sat\n3,Sun\n"):
    env.app.include_router(router,prefix="/api/v1")
    dataset=upload(env,data).json()
    response=env.client.post('/api/v1/reports',headers=HEADERS,json={"title":"Draft","dataset_id":dataset['id']})
    assert response.status_code==201,response.text
    report=response.json()
    return report, dataset


def definition():
    return {"version":1,"filters":[{"type":"category","column":"c1","values":["Sun"]}],"blocks":[
        {"id":"metric","type":"metric","title":"Total","operation":"sum","column":"c0","group_by":None},
        {"id":"chart","type":"chart","title":"By day","chart_type":"bar","operation":"sum","column":"c0","group_by":"c1"},
        {"id":"table","type":"table","title":"Largest","sort_by":"c0","direction":"desc","limit":1},
        {"id":"note","type":"note","title":"Context","text":"A plain note.\n<script>not executable</script>"},
    ]}


def save(env,report,dataset,doc=None,revision=1,**changes):
    body={"title":"My saved report","expected_revision":revision,"expected_sha256":dataset['sha256'],"definition":doc or definition()}
    return env.client.patch(f"/api/v1/reports/{report['id']}/editor",headers=HEADERS,json=body|changes)


def evaluate(env,report,dataset,revision=2):
    return env.client.post(f"/api/v1/reports/{report['id']}/evaluate",headers=HEADERS,json={"expected_revision":revision,"expected_sha256":dataset['sha256']})


def test_existing_draft_loads_empty_and_preserves_identity(env):
    report,dataset=setup(env)
    response=env.client.get(f"/api/v1/reports/{report['id']}/editor")
    assert response.status_code==200,response.text
    result=response.json()
    assert result['revision']==1
    assert result['definition']=={"version":1,"blocks":[],"filters":[]}
    assert result['dataset_id']==dataset['id']
    assert response.headers['cache-control']=='no-store'


def test_all_four_blocks_save_reload_filter_and_receipts(env):
    report,dataset=setup(env)
    saved=save(env,report,dataset)
    assert saved.status_code==200,saved.text
    assert saved.json()['revision']==2
    loaded=env.client.get(f"/api/v1/reports/{report['id']}/editor").json()
    assert loaded['definition']['blocks'][3]['text']==definition()['blocks'][3]['text']
    response=evaluate(env,report,dataset)
    assert response.status_code==200,response.text
    output=response.json()
    assert output['complete'] and output['revision']==2
    assert len(output['results'])==3
    metric,chart,table=output['results']
    assert metric['result']['rows'][0]['value']==chart['result']['rows'][0]['value']=='4'
    assert table['result']['rows'][0]['record_number']==3
    assert all(block['receipt']['report_revision']==2 for block in output['results'])
    assert metric['receipt']['excluded_by_filters']==1
    assert table['receipt']['included_rows']==1 and table['receipt']['excluded_rows']==2


def test_reorder_and_remove_persist_exactly(env):
    report,dataset=setup(env)
    doc=definition();doc['blocks']=[doc['blocks'][3],doc['blocks'][0],doc['blocks'][2]]
    assert save(env,report,dataset,doc).status_code==200
    result=env.client.get(f"/api/v1/reports/{report['id']}/editor").json()
    assert [block['id'] for block in result['definition']['blocks']]==['note','metric','table']


def test_stale_save_and_evaluation_do_not_overwrite(env):
    report,dataset=setup(env)
    assert save(env,report,dataset).status_code==200
    assert save(env,report,dataset,title='Stale overwrite').status_code==409
    assert evaluate(env,report,dataset,revision=1).status_code==409
    saved=env.client.get(f"/api/v1/reports/{report['id']}/editor").json()
    assert saved['title']=='My saved report' and saved['revision']==2


def test_workspace_rename_also_bumps_revision(env):
    report,dataset=setup(env)
    assert env.client.patch(f"/api/v1/reports/{report['id']}",headers=HEADERS,json={'title':'Renamed elsewhere'}).status_code==200
    assert save(env,report,dataset).status_code==409
    assert env.client.get(f"/api/v1/reports/{report['id']}/editor").json()['revision']==2


def test_owner_anonymous_and_protection_enforced(env):
    report,dataset=setup(env)
    env.state.current=env.second
    assert env.client.get(f"/api/v1/reports/{report['id']}/editor").status_code==404
    assert save(env,report,dataset).status_code==404
    assert evaluate(env,report,dataset,1).status_code==404
    env.state.current=env.first
    assert env.client.patch(f"/api/v1/reports/{report['id']}/editor",json={}).status_code==403
    assert env.client.post(f"/api/v1/reports/{report['id']}/evaluate",json={}).status_code==403
    del env.app.dependency_overrides[get_current_user]
    assert env.client.get(f"/api/v1/reports/{report['id']}/editor").status_code==401


def test_unknown_columns_owner_and_dataset_changes_reject(env):
    report,dataset=setup(env)
    assert save(env,report,dataset,owner_id=str(env.second.id)).status_code==422
    assert save(env,report,dataset,dataset_id=str(uuid.uuid4())).status_code==422
    assert save(env,report,dataset,expected_sha256='0'*64).status_code==409
    doc=definition();doc['blocks'][0]['column']='c99'
    assert save(env,report,dataset,doc).status_code==422


def test_invalid_schema_limits_and_duplicate_ids_reject(env):
    report,dataset=setup(env)
    doc=definition();doc['blocks'][3]['id']='metric'
    assert save(env,report,dataset,doc).status_code==422
    doc=definition();doc['blocks'][2]['limit']=101
    assert save(env,report,dataset,doc).status_code==422
    doc=definition();doc['blocks'][0]['sql']='SELECT 1'
    assert save(env,report,dataset,doc).status_code==422
    doc=definition();doc['blocks']=[dict(id=f'n{i}',type='note',text='a'*9000) for i in range(8)]
    response=save(env,report,dataset,doc)
    assert response.status_code==422 and '64 KiB' in response.json()['detail']


def test_bad_block_is_local_and_draft_is_still_editable(env):
    report,dataset=setup(env)
    doc=definition();doc['blocks'][0]['column']='c1'
    assert save(env,report,dataset,doc).status_code==200
    response=evaluate(env,report,dataset).json()
    assert response['complete'] is False and response['results']==[]
    assert response['errors']==[{'block_id':'metric','message':'Sum and average need a number column.'}]
    assert save(env,report,dataset,definition(),revision=2).status_code==200
    assert evaluate(env,report,dataset,revision=3).json()['complete'] is True


def test_note_only_and_empty_reports_do_not_fabricate_queries(env,monkeypatch):
    report,dataset=setup(env)
    doc={'blocks':[{'id':'n','type':'note','text':'Only context'}],'filters':[]}
    assert save(env,report,dataset,doc).status_code==200
    def forbidden(*args):raise AssertionError('A note must not execute a numerical query')
    monkeypatch.setattr(report_editor,'evaluate_dataset',forbidden)
    assert evaluate(env,report,dataset).json()['results']==[]
    assert save(env,report,dataset,{'blocks':[],'filters':[]},revision=2).status_code==200
    assert evaluate(env,report,dataset,revision=3).json()['complete']


def test_date_filter_utc_and_line_chart_use_saved_definition(env):
    report,dataset=setup(env,b'amount,date\n1,2026-10-01T23:30:00-02:00\n2,2026-10-02T12:00:00Z\n3,2026-10-03\n')
    doc={'blocks':[{'id':'line','type':'chart','title':'Timeline','chart_type':'line','operation':'sum','column':'c0','group_by':'c1'}],
        'filters':[{'type':'date_range','column':'c1','start':'2026-10-02','end':'2026-10-02'}]}
    assert save(env,report,dataset,doc).status_code==200
    response=evaluate(env,report,dataset).json()['results'][0]
    assert [row['value'] for row in response['result']['rows']]==['1','2']
    assert response['receipt']['included_rows']==2
    assert response['receipt']['excluded_by_filters']==1


def test_count_average_numeric_and_missing_filters(env):
    report,dataset=setup(env,b'amount,day\n1,Sun\n,Sun\n3,Sat\n')
    doc={'blocks':[{'id':'avg','type':'metric','operation':'average','column':'c0'}, {'id':'count','type':'metric','operation':'count'}],
        'filters':[{'type':'missing','column':'c0','missing':False},{'type':'number_range','column':'c0','minimum':'1.5'}]}
    assert save(env,report,dataset,doc).status_code==200
    avg,count=evaluate(env,report,dataset).json()['results']
    assert avg['result']['rows'][0]['value']=='3.000000'
    assert count['result']['rows'][0]['value']==1


@pytest.mark.skipif(os.getenv('TRACE_AUTH_EMBEDDED_DB')=='1',reason='Requires native concurrent PostgreSQL connections')
def test_two_simultaneous_saves_have_only_one_winner(env):
    report,dataset=setup(env)
    barrier=Barrier(2)
    def attempt(title):
        barrier.wait(timeout=10)
        return save(env,report,dataset,title=title).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(attempt,title) for title in ['First','Second']]
        assert sorted(future.result(timeout=20) for future in futures)==[200,409]
    with env.db() as db:
        assert db.get(Report,uuid.UUID(report['id'])).revision==2


def test_generated_migration_preserves_existing_drafts_and_is_reversible(env,monkeypatch,tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect,text

    report,_=setup(env)
    with env.db() as db:engine=db.get_bind()
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE reports DROP COLUMN definition'))
        connection.execute(text('ALTER TABLE reports DROP COLUMN revision'))
        connection.execute(text("ALTER TABLE reports ADD COLUMN custom_test TEXT DEFAULT 'kept'"))
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('previous_phase')"))
    config=Config(str(tmp_path/'alembic.ini'))
    command.init(config,str(tmp_path/'migrations'))
    (tmp_path/'alembic.ini').write_text('[alembic]\nscript_location = %(here)s/migrations\n')
    (tmp_path/'migrations/versions/previous.py').write_text("revision='previous_phase'\ndown_revision=None\ndef upgrade():pass\ndef downgrade():pass\n")
    (tmp_path/'migrations/env.py').write_text('from alembic import context\nconnection=context.config.attributes["connection"]\ncontext.configure(connection=connection)\nwith context.begin_transaction():context.run_migrations()\n')
    script=Path(__file__).resolve().parents[1]/'scripts/prepare_phase6_migration.py'
    spec=importlib.util.spec_from_file_location('phase6_migration_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'engine',engine)
    monkeypatch.chdir(tmp_path)
    module.main()
    files=list((tmp_path/'migrations/versions').glob('*trace_phase6_editor*'))
    assert len(files)==1
    assert "down_revision = 'previous_phase'" in files[0].read_text()
    config=Config(str(tmp_path/'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection']=connection
        command.upgrade(config,'head')
        saved=connection.execute(text('SELECT title,definition,revision,custom_test FROM reports WHERE id=:id'),{'id':uuid.UUID(report['id'])}).one()
        assert tuple(saved)==('Draft',{},1,'kept')
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()=='trace_phase6_editor'
    module.main()  # Must not generate a duplicate revision.
    assert len(list((tmp_path/'migrations/versions').glob('*trace_phase6_editor*')))==1
    with engine.begin() as connection:
        config.attributes['connection']=connection
        command.downgrade(config,'previous_phase')
        assert not {'definition','revision'} & {item['name'] for item in inspect(connection).get_columns('reports')}
        assert connection.execute(text('SELECT title,custom_test FROM reports')).one()==('Draft','kept')
