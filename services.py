from redis import Redis
from rq import Queue
from juniper_cfg.utils import Utils
from juniper_cfg.apiutils import APIUtils

# Initialize single instances of your tools
apiut = APIUtils()
ut = Utils()

# RQ Setup
sync_redis = Redis(host='localhost', port=6379)
q = Queue('juniper', connection=sync_redis)