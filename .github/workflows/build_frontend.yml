name: Build Front End
on:
  pull_request:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [22.x]
    steps:
      - uses: actions/checkout@v4
      - name: Use Node.js ${{ matrix.node-version }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - name: Install dependencies
        run: npm install
      - name: Build Django front end
        run: npm run build
      - name: Install Jest tools
        run: npm install --save-dev jest ts-jest @types/jest
      - name: Check types
        run: npm run type-check
      - name: Install opie-y-provider dependencies
        run: npm install
        working-directory: ./opie-y-provider
      - name: Check opie-y-provider types
        run: npm run build
        working-directory: ./opie-y-provider
      - name: Install front end dependencies
        run: npm install
        working-directory: ./frontend
      - name: Build Vite front end and run type checks
        run: npm run build
        working-directory: ./frontend
        env:
          VITE_APP_BASE_URL: http://localhost:8000
