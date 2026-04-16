const CACHE_NAME = 'mind-state-siborg-cache-v6';

const urlsToCache = [
  '/',
  '/index.html',
  '/privacy.html',
  '/manifest.json',
  '/icon/icon-192x192.png',
  '/icon/icon-512x512.png'
];

// Install
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.all(
        urlsToCache.map(url => {
          return fetch(url)
            .then(response => {
              if (!response.ok) {
                throw new Error(`Failed to fetch ${url}`);
              }
              return cache.put(url, response);
            })
            .catch(err => {
              console.warn('Not cached:', url, err);
            });
        })
      );
    })
  );
});

// Fetch
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});

// Activate
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames =>
      Promise.all(
        cacheNames.map(cacheName => {
          if (!cacheWhitelist.includes(cacheName)) {
            return caches.delete(cacheName);
          }
        })
      )
    )
  );
});
