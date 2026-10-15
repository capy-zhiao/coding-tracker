# Web image: build the Vite app with Node, then serve it with Caddy, which also proxies
# /api to the backend and handles HTTPS (see Caddyfile).
#   docker build -t leetcode-tracker-web frontend
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv
