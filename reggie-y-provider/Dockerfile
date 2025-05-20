# ---- Base build stage ----
    FROM node:20-alpine AS y-provider-builder

    WORKDIR /home/y-provider
    
    # Copy main project package files
    COPY package.json yarn.lock ./
    
    # Copy eslint-config-impress package.json to satisfy Yarn (local file: dependency)
    COPY packages/eslint-config-impress/package.json ./packages/eslint-config-impress/package.json
    
    # Install only production dependencies
    ARG NODE_ENV=production
    ENV NODE_ENV=${NODE_ENV}
    RUN yarn install --frozen-lockfile --production=true
    
    # Copy source files
    COPY . .
    
    # Build the project
    RUN yarn build
    
    # ---- Final runtime stage ----
    FROM node:20-alpine AS y-provider
    
    WORKDIR /home/y-provider
    
    # Copy only the built output
    COPY --from=y-provider-builder /home/y-provider/dist ./dist
    
    # Copy production package files again
    COPY package.json yarn.lock ./
    
    # Copy eslint-config-impress package.json again to satisfy yarn install
    COPY packages/eslint-config-impress/package.json ./packages/eslint-config-impress/package.json
    
    # Install only production dependencies
    ARG NODE_ENV=production
    ENV NODE_ENV=${NODE_ENV}
    RUN yarn install --frozen-lockfile --production=true
    
    # Remove npm to reduce CVEs
    RUN rm -rf /usr/local/bin/npm /usr/local/lib/node_modules/npm
    
    # Copy the entrypoint
    COPY ./docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint
    RUN chmod +x /usr/local/bin/entrypoint
    
    ENTRYPOINT ["/usr/local/bin/entrypoint"]
    
    # Start the server
    CMD ["yarn", "start"]
    