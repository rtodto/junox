from redis import Redis
from rq.job import Job

# 1. Connect to the same Redis you used for enqueuing
redis_conn = Redis(host='localhost', port=6379)

# 2. Fetch the job using its unique ID
job_id = "e0cd7894-b1fb-4b09-b9b6-72bdea395180"
job = Job.fetch(job_id, connection=redis_conn)

# 3. Access the data
if job.is_finished:
    # return_value() is the standard for RQ >= 1.12
    print(f"Result: {job.return_value()}") 
else:
    print(f"Status: {job.get_status()}")
