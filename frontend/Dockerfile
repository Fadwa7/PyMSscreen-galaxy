# Build step
FROM node:18 as builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install
RUN npm install @babel/runtime 

COPY . .
RUN npm run build

# Serve using nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Optional: Custom nginx config (if needed)
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

