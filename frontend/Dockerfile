# frontend/Dockerfile
FROM node:18-alpine
WORKDIR /app

COPY package*.json ./
RUN npm install

# Add missing peer dependencies for react-select, etc.
RUN npm install @babel/runtime @emotion/react @emotion/cache

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev","--","--host"]
