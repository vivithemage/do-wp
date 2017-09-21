import digitalocean
import logging
import paramiko
import time
import shutil
import random
import string

def password_generator(size=24, chars=string.ascii_uppercase + string.digits):
    generated_password = ''.join(random.choice(chars) for x in range(size))

    return generated_password


'''
Puts the wp installation and puts it on the server.
It wraps the folder up, uploads and extracts.
'''
class SiteTransport:
    def __init__(self, client, gui_variables):
        self.client = client
        self.installation_path = gui_variables['installation_path']
        self.site_url = gui_variables['site_url']

    def _prepare(self):
        zip_path = self.installation_path
        shutil.make_archive(zip_path, 'zip', self.installation_path)

        return zip_path + '.zip'

    def upload(self):
        remote_zip_path = '/root/' + self.site_url + '.zip'
        zip_path = self._prepare()

        self.client.get_transport()
        sftp = self.client.open_sftp()
        sftp.put(zip_path , remote_zip_path)

        self.remote_extract()

        return True

    def remote_extract(self):
        return True


class NginxConfigTransport:
    def __init__(self):
        self.config_path = 'config/nginx_config.conf'

    def generate(self):
        self.vps_nginx_config_path
        self.logger.info('Generating server config')

    def upload(self):
        self.logger.info('Uploading server config')


'''
Using the ssh details, log in over ssh and Configure the server to suit.
'''
class Configuration():
    def __init__(self, ipv4_address, ssh_username, ssh_password, vps, gui_variables):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.ssh_init_path = 'config/init.sh'
        self.ipv4_address = ipv4_address
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.gui_variables = gui_variables
        self.vps_instance = vps
        self.vps_mysql_password = None

    '''
    Checks each line for any variables that need replacing.
    For instance {site_url} would need replacing with whatever was entered in the ui.
    '''
    def replace_ssh_command_variables(self, line):
        return line

    '''
    Fetch the remote password on the production server
    '''
    def get_mysql_password(self, ssh_client):
        command = 'cat /root/.digitalocean_password'
        stdin, stdout, stderr = ssh_client.exec_command(command)
        result = stdout.readlines()
        stripped_result = result[0].replace('root_mysql_pass=', '')
        self.vps_mysql_password = stripped_result.replace('"', '')


    def run_init_commands(self, ssh_client):
        with open(self.ssh_init_path) as f:
            for line in f:
                amended_line = self.replace_ssh_command_variables(line)
                stdin, stdout, stderr = ssh_client.exec_command(amended_line)
                self.logger.info(stdout.readlines())

        ssh_client.close()

    '''
    Opens up ssh client and returns client to execute commands
    '''
    def open_ssh_connection(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.logger.info("connecting to " + str(self.ipv4_address) + " with: root/" + self.ssh_password)
        try:
            client.connect(self.ipv4_address, port=22, username=self.ssh_username, password=self.ssh_password,
                           allow_agent=True)
        except paramiko.AuthenticationException:
            self.logger.info("Issue connecting to server over ssh, trying again")

        return client

    '''
    Wait a while after the server is spun up so it has a chance to boot.
    Play about with this, sometime the servers don't spin up under 60 seconds
    for whatever reason so just try again.
    '''
    def grace_period(self):
        grace_period_seconds = 60
        max_check_seconds = 60

        for seconds in range(0, max_check_seconds):
            time.sleep(1)
            if self.vps_instance.ready():
                self.logger.info('Server spin up is complete!')
                break
            else:
                self.logger.info("Server not ready, waiting: %d seconds so far" % (seconds))

        self.logger.info('Server spun up, additional %d second ssh grace period: ' % grace_period_seconds)
        time.sleep(grace_period_seconds)


    '''
    Additional configuration to prepare the site to host wp
    '''
    def run(self):
        self.grace_period()
        ssh_client = self.open_ssh_connection()

        transport = SiteTransport(ssh_client, self.gui_variables)
        transport.upload()

        webserver_config = NginxConfigTransport()
        webserver_config.upload()

        self.get_mysql_password(ssh_client)
        self.run_init_commands(ssh_client)

        ssh_client.close()

'''
Does all the vitals to get the server up and running and returns the details to make a ssh connection.
'''
class ServerInit:
    def __init__(self, variables):
        super(ServerInit, self).__init__()

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        #TODO pull from field
        self.api_key = "20f03956273725fe5a6133e5ebcb93de2ea5c454cd8461881ae6cff96c43d50a"

        self.username = 'root'
        self.password = password_generator()
        self.ip_address_v4 = None
        user_data = self.get_user_data()

        '''
        Digitalocean server details
        '''
        DO_server_image = 'lemp-16-04';
        DO_server_name = variables['site_url'] + '-wp'
        DO_region = 'lon1'
        DO_ram = '512mb'

        # TODO enable v6 address and monitoring
        self.instance = digitalocean.Droplet(token=self.api_key,
                                             name=DO_server_name,
                                             region=DO_region,
                                             image=DO_server_image,
                                             size_slug=DO_ram,
                                             user_data=user_data)

    def get_user_data(self):
        cloud_init_path = 'config/user_data.txt'

        with open(cloud_init_path, 'r') as cloud_init_file:
            user_data_raw = cloud_init_file.read()
            user_data = user_data_raw.replace('{generated_password}', self.password)
            return user_data

    '''
    !!CAUTION!! Never use this on a production account.
    Used to destroy all servers during development to save coinage
    '''
    def dev_housekeeping(self):
        manager = digitalocean.Manager(token=self.api_key)
        my_droplets = manager.get_all_droplets()
        for droplet in my_droplets:
            droplet.destroy()

    '''
    Once the api returns 'completed', the droplet is up and running
    '''
    def ready(self):
        success_message = 'completed'
        actions = self.instance.get_actions()

        for action in actions:
            action.load()
            if action.status == success_message:
                return True
            else:
                self.logger.info('Current Status: ' + action.status)
                return False

    '''
    Creates the server instance
    '''
    def spin_up(self):
        self.instance.create()
        self.instance.load()
        self.ip_address_v4 = self.instance.ip_address

    def run(self):
        self.logger.info("Removing old machines")
        self.dev_housekeeping()

        self.logger.info('Starting spin up')
        self.spin_up()
        self.logger.info('Successfully spun up server')

        return self.ip_address_v4, self.username, self.password
