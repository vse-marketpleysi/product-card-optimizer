import configobj
import os

from src.utils.json_utils import load_json, save_json, create_json_if_not_exist
from dateutil.parser import parse
from datetime import datetime, timedelta
import pytz

USAGE_DB = 'usage_db.json'


class UsageLimiter:
    config_path: str
    usage_db_path: str
    
    def __init__(self, config_path, db_path_base):
        self.config_path = config_path
        self.usage_db_path = os.path.join(db_path_base, USAGE_DB)
    
    def get_limit(self, user_id):
        user_id = str(user_id)
        usage_config = configobj.ConfigObj(self.config_path)
        daily_usage_limit = int(usage_config['daily_usage_limit'])
        return daily_usage_limit

    def can_use(self, user_id):
        user_id = str(user_id)
        daily_usage_limit = self.get_limit(user_id)

        admins = configobj.ConfigObj(self.config_path)['admins']
        if user_id in admins:
            return True

        create_json_if_not_exist(
            self.usage_db_path, 
            {
                'daily_usage': {}
            }
        )
        usage_db = load_json(self.usage_db_path)
        
        now = datetime.now(pytz.timezone('Europe/Moscow'))

        if user_id in usage_db['daily_usage']:
            daily_usage = usage_db['daily_usage'][user_id]

            daily_usage_filtered = [t for t in daily_usage if parse(t) > now - timedelta(days=1)]
            if len(daily_usage_filtered) >= daily_usage_limit:
                return False
        return True


    def use(self, user_id):
        user_id = str(user_id)
        
        if not self.can_use(user_id):
            return False

        usage_db = load_json(self.usage_db_path)
        
        now = datetime.now(pytz.timezone('Europe/Moscow'))

        if user_id not in usage_db['daily_usage']:
            usage_db['daily_usage'][user_id] = []

        usage_db['daily_usage'][user_id].append(str(now))

        save_json(self.usage_db_path, usage_db)
        return True
