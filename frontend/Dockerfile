FROM node:22-bookworm

WORKDIR /app

# api-client is listed as a local file dependency in the root package.json:
# "api-client": "file:./api-client"
# The frontend's package.json (if it also needs it directly and it's not hoisted)
# would also refer to it. For building the frontend standalone, if it uses the api-client
# directly through a relative path from the `frontend` dir to the root `api-client` dir,
# we need to ensure the paths are set up correctly.

# Let's assume the build context for this Dockerfile is the root of the repository.
# And the frontend needs access to the top-level api-client.

# Copy essential configuration files first
COPY frontend/package.json frontend/package-lock.json* frontend/tsconfig.json frontend/vite.config.ts ./
# Copy the api-client, assuming it's referenced via a relative path from frontend code
# e.g., import ... from '../../api-client'
# To make this work inside Docker where WORKDIR is /app (representing the frontend app's root),
# we might need to adjust paths or copy api-client to a location accessible from /app.
# For simplicity, if api-client is a true local dependency for `npm install`
# it should be copied relative to where `package.json` is.
# The root `package.json` has "api-client": "file:./api-client".
# The `frontend/package.json` does not explicitly list `api-client`.
# It's likely consumed via the root build process or directly imported.

# If this Dockerfile is meant to build `frontend` standalone, and `frontend`
# imports from `api-client` using relative paths like `../api-client`,
# then the structure inside Docker needs to mirror that.

# Option 1: Build frontend in its own directory, assuming `api-client` is resolved by Node's module system
# if `frontend/package.json` had ` "api-client": "file:../api-client" `
# WORKDIR /app/frontend
# COPY api-client /app/api-client
# COPY frontend/package.json frontend/package-lock.json* ./
# RUN npm install
# COPY frontend /app/frontend

# Option 2: A simpler approach for a standalone frontend build,
# assuming the context is the `frontend` directory itself when building this image.
# Or, if context is root, explicitly copy only necessary parts.

# Let's stick to WORKDIR /app representing the root of what this Docker image is concerned with,
# which is the frontend application.

# Copy api-client to a place where frontend build can access it, if necessary.
# This depends on how frontend code imports from api-client.
# Given `frontend/Dockerfile` and `api-client` at root, and frontend code in `frontend/src`,
# a typical import might be `import ... from '../../api-client'`.
# If we set WORKDIR /app for frontend's own files, then api-client needs to be one level up.
# Let's simplify and assume for a standalone build, api-client is copied into the app structure.
COPY api-client /app/api-client

# Copy frontend specific package files
COPY frontend/package.json frontend/package-lock.json* ./
# If tsconfig, vite.config etc. are needed for install or build steps directly
COPY frontend/tsconfig.json ./
COPY frontend/vite.config.ts ./
COPY frontend/postcss.config.js ./
COPY frontend/.env.example ./ # If scripts need it

RUN npm install

# Copy the rest of the frontend application's source code
COPY frontend/public ./public
COPY frontend/src ./src
COPY frontend/index.html ./

# The original Dockerfile.web's node stage copies the root package.json, then assets, then api-client,
# then runs npm install, then copies the whole repo, then npm run build.
# This frontend/Dockerfile is for a different purpose, perhaps local dev or a specific frontend build.

# If this is for building the frontend (e.g. for Vercel or Netlify deployment):
# RUN npm run build
# (Then serve static files from 'dist' or 'build' directory)

# If this is for development:
# EXPOSE 5173 # Common for Vite
# CMD ["npm", "run", "dev"]

# For now, focusing on cache optimization for `npm install`.
# The final COPY . /code/ was problematic. This structure is more standard.
