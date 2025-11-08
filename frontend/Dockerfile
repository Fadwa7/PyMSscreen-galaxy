# Build step
FROM node:20-bullseye AS frontend-builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install -g npm@11
RUN npm install -D patch-package --no-audit --no-fund \
 && npm install --no-audit --no-fund

 RUN npm install @babel/runtime 

COPY . .
RUN npm run build

# Serve using nginx
FROM mirror.gcr.io/library/nginx:alpine

COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Optional: Custom nginx config (if needed)
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

