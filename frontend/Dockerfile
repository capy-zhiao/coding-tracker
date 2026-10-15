# Frontend image: build the Vite app with Node, then serve it with nginx, which also
# proxies /api to the backend (the same mapping as the dev proxy in vite.config.ts).
#   docker build -t leetcode-tracker-web frontend
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
