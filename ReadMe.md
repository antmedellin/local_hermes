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


added
https://hermes-tutorials.dev/blog/kanban-multi-agent-workflows/
https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban


mhc794@DW78894:~/test/local_hermes$ docker exec -it hermes 
hermes kanban init
hermes kanban list
hermes gateway start
hermes kanban create "create hellow world 1 docx file" --assignee default
hermes gateway restart

/learn the verified troubleshooting workflow from this session. Exclude secrets and temporary values. Include symptoms, diagnosis, fix, verification, and rollback.


hermes doctor 
hermes doctor --fix
npx agent-browser doctor
npm audit fix


git remote add upstream https://github.com/NousResearch/hermes-agent.git
git remote -v
git fetch upstream
git checkout main
git merge upstream/main

git remote add upstream https://github.com/HKUDS/LightRAG.git
git remote -v
git fetch upstream
git checkout main
git merge upstream/main


wsl -d Ubuntu -- bash -lc "cd ~/test/local_hermes/hermes-agent ; docker compose -f docker-compose.windows.yml build"
make sure memory is updated so references correct location