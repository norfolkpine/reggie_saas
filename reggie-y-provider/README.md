# reggie-y-provider
Command to output directory structure
```
tree -L 3 -I 'node_modules|.git' > tree_output.txt
```

Task | Command
Build your docker image | docker build -t y-provider .
Run it | docker run -p 1234:1234 y-provider (assuming 1234 is your WebSocket port)

docker compose up --build
docker compose build --no-cache
docker compose up

## Test locally without Docker
```
yarn install
rm -rf dist
yarn build
yarn start
```


