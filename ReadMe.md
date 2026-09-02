git clone https://github.com/antmedellin/local_hermes.git
git submodule update --init --recursive --remote



to update containers: docker compose pull
to build containers: docker compose build
to start: docker compose up -d 
to stop: docker compose stop
use hermes from terminal: docker exec -it hermes /bin/bash
use hermes from browser: http://localhost:9119
username for dashboard: admin, password: password
