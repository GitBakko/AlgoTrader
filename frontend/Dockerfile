# syntax=docker/dockerfile:1

# ===== Build Stage =====
FROM node:22-alpine AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build for production
RUN npx ng build --configuration=production

# ===== Production Stage =====
FROM nginx:alpine AS production

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build output
COPY --from=build /app/dist/coreui-free-angular-admin-template/browser /usr/share/nginx/html

EXPOSE 4321

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:4321/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
