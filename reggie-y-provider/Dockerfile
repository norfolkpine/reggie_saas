# ---- Base build stage ----
FROM node:20-alpine AS y-provider-builder

WORKDIR /home/y-provider

# Copy main project package files
COPY reggie-y-provider/package.json reggie-y-provider/yarn.lock ./
# Copy all local dependency folders before install
COPY reggie-y-provider/packages ./packages

# Install all dependencies (dev + prod)
ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}
RUN yarn install --frozen-lockfile || cat yarn-error.log

RUN yarn list typescript && ls -l node_modules/.bin && node_modules/.bin/tsc --version || echo "tsc not found"

# Copy the rest of the source files
COPY reggie-y-provider/. .

# Install typescript global (debug only)
RUN yarn global add typescript

# Build the project
RUN yarn build

# ---- Final runtime stage ----
FROM node:20-alpine AS y-provider

WORKDIR /home/y-provider

# Copy only the built output
COPY --from=y-provider-builder /home/y-provider/dist ./dist

# Copy production package files again
COPY reggie-y-provider/package.json reggie-y-provider/yarn.lock ./

# Copy eslint-config-impress package.json again to satisfy yarn install
COPY reggie-y-provider/packages/eslint-config-impress/package.json ./packages/eslint-config-impress/package.json

# Install only production dependencies
ARG NODE_ENV=production    
# Remove npm to reduce CVEs
RUN rm -rf /usr/local/bin/npm /usr/local/lib/node_modules/npm

# Copy the entrypoint
COPY reggie-y-provider/docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint

ENTRYPOINT ["/usr/local/bin/entrypoint"]
    
# Start the server
CMD ["yarn", "start"]