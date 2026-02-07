import redis

# Connect to localhost:6379
r = redis.Redis(host='127.0.0.1', port=6379, db=0)

# Set Key
r.set('python_test_key', 'Inserted via Python')

# Get Key
print(r.get('python_test_key'))

