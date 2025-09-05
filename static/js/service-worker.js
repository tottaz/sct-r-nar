self.addEventListener("install", event => {
  event.waitUntil(
    caches.open("sattmal-cache").then(cache => {
      return cache.addAll([
          '/', 
          '/static/js/bootstrap.bundle.min.js', 
          '/static/css/style.css'
      ]);
    })
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});
