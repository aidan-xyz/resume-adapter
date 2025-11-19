import multiprocessing

# Timeout settings
timeout = 300
graceful_timeout = 300
keepalive = 5

# Worker settings
workers = 1
worker_class = 'sync'

# Logging
loglevel = 'info'
accesslog = '-'
errorlog = '-'

# Bind
bind = '0.0.0.0:8080'
