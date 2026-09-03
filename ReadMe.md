git clone https://github.com/antmedellin/local_hermes.git
git submodule update --init --recursive --remote

create ollama storage folder
cd local_hermes
mkdir ollama_storage

to update containers: docker compose pull
to build containers: docker compose build
to start: docker compose up -d 
to stop: docker compose stop
use hermes from terminal: docker exec -it hermes /bin/bash
use hermes from browser: http://localhost:9119
username for dashboard: admin, password: password


hermes exec
/opt/hermes/.venv/bin/python -m ensurepip --upgrade
/opt/hermes/.venv/bin/python -m pip install python-docx lxml

verify working by 
/opt/hermes/.venv/bin/python -c "import docx; print(docx.__version__)"

/app/lightrag/kg/milvus_impl.py
update file to fix variable to below 

search_params = {
    "metric_type": self.index_config.metric_type,
    "params": {
        **search_params_base.get("params", {}),
    },
}
`