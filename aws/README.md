# AWS runbook: the `mccr` EC2 instance

This is the working notes for the one EC2 instance that runs our experiments. Everything here is a command for a person to run. Check each command before you run it: the account belongs to the university.

## Facts about our setup

| Item | Value |
|---|---|
| Region | `us-west-2` (`us-east-1` is blocked by the organization) |
| New instance ID (`mccr-2`, the commands below use this one) | `i-03014c108a7b7b4d1` |
| Old instance ID (`mccr`, kept, not deleted) | `i-0200db8f0268c7340` |
| Type | `t3.large` (2 vCPU, 8 GB RAM), about $0.08 per hour while running |
| Disk | 20 GB gp3, deleted when the instance is terminated |
| Image | Old instance: Ubuntu 24.04, `ami-08cf17e3856f70154`. New instance: Ubuntu 26.04.1 LTS, system Python 3.14, project `.venv` on Python 3.12.16 through `uv` |
| Key pair | `mccr-key`, private key at `~/.ssh/mccr-key.pem` (never commit it) |
| Security group | `sg-0e21f5c11b37dd135`, SSH (port 22) from one IP only |
| SSH alias | Old instance: `mccr` in `~/.ssh/config` (also the host name in VS Code). New instance: `mccr-2` |
| Working folder on the instance | `~/mcc-recovery` (a clone of this repo) |

## Credentials

The AWS keys are temporary. They are in `.env` at the repo root (git ignores it) and they stop working after a few hours. When a command says `ExpiredToken`, get new keys and replace the three values in `.env`. A running instance is not affected when the keys expire.

Load them before every AWS command, in the same terminal:

```bash
set -a; source .env; set +a
```

Check that they work:

```bash
aws sts get-caller-identity
```

## Daily commands (run on your Mac)

Show the instance state and its public IP:

```bash
aws ec2 describe-instances --region us-west-2 --instance-ids i-03014c108a7b7b4d1 \
  --query 'Reservations[0].Instances[0].[State.Name,PublicIpAddress]' --output text
```

Start it:

```bash
aws ec2 start-instances --region us-west-2 --instance-ids i-03014c108a7b7b4d1
aws ec2 wait instance-running --region us-west-2 --instance-ids i-03014c108a7b7b4d1
```

After every start the public IP changes. Run the "show" command again, then put the new IP in `~/.ssh/config` under `Host mccr-2` (`HostName`). VS Code and `ssh mccr-2` use that entry.

Stop it (do this when you finish for the day):

```bash
aws ec2 stop-instances --region us-west-2 --instance-ids i-03014c108a7b7b4d1
```

Connect:

```bash
ssh mccr-2
```

The old instance stays available. To use it, replace the instance ID in the commands above with `i-0200db8f0268c7340`, and use `Host mccr` and `ssh mccr`. Stop it when you are not using it, because a running instance costs money.

## What happens when you stop, reboot or terminate

| Action | Instance | Files on the disk | Public IP | Cost |
|---|---|---|---|---|
| Stop | Off | Kept | Released. A new one is given on start | No compute cost. The 20 GB disk still costs about $1.60 per month |
| Start (after stop) | On | Still there | New IP | About $0.08 per hour |
| Reboot | Restarts | Kept | Same | Same as running |
| Terminate | Deleted for good | Deleted with the instance | Released | Nothing more |

What stop does not keep: anything running. A `tmux` session or a running experiment ends, and so does everything in memory. Start long runs again after a start, and make the runner resume (finished runs are skipped).

Terminate cannot be undone. Before you terminate, push all code to GitHub and copy the `runs/` folder off the instance (see "Get results off the instance").

## Create a new instance

Use this if the old one was terminated. The key pair and security group already exist, so the launch needs only this one command. If the old instance was in the same subnet, nothing else changes.

```bash
aws ec2 run-instances --region us-west-2 \
  --image-id ami-08cf17e3856f70154 --instance-type t3.large \
  --key-name mccr-key --security-group-ids sg-0e21f5c11b37dd135 \
  --subnet-id subnet-0fd472c7b2f05f1f8 --associate-public-ip-address \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=mccr}]' \
  --query 'Instances[0].InstanceId' --output text
```

Copy the new instance ID into the table above and into the commands in this file. Then do "Set up the instance" below.

If SSH times out, your own IP probably changed. Find it, then open port 22 for the new address:

```bash
curl -s https://checkip.amazonaws.com
aws ec2 authorize-security-group-ingress --region us-west-2 --group-id sg-0e21f5c11b37dd135 \
  --protocol tcp --port 22 --cidr <YOUR_IP>/32
```

Remove the old address with `revoke-security-group-ingress` and the same arguments.

## Set up the instance (once per instance)

Run these on the instance (`ssh mccr`).

1. Check that git is installed, and set who you are for commits:

   ```bash
   git --version
   git config --global user.name "<your name>"
   git config --global user.email "<your email>"
   ```

2. Make a key that belongs to this instance only, and print the public half:

   ```bash
   ssh-keygen -t ed25519 -C "mccr-ec2" -f ~/.ssh/github_mccr -N ""
   cat ~/.ssh/github_mccr.pub
   ```

3. In GitHub, open the repo, then Settings > Deploy keys > Add deploy key. Paste the public key and tick "Allow write access". A deploy key works for this one repo only, so no personal password or token is stored on the university server.

4. Tell SSH to use that key for GitHub:

   ```bash
   printf 'Host github.com\n    IdentityFile ~/.ssh/github_mccr\n    IdentitiesOnly yes\n' >> ~/.ssh/config
   ssh -T git@github.com
   ```

   The last command should say you authenticated. It is normal that it also says GitHub does not provide shell access.

5. Clone the repo and build the environment inside it:

   ```bash
   cd ~
   git clone git@github.com:Aleptonic/mansi-project.git mcc-recovery
   cd mcc-recovery
   sudo apt-get update && sudo apt-get install -y tmux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ~/.local/bin/uv venv --python 3.12 --seed .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m pytest -q
   ```

6. Store the TritonAI key outside the repo, readable by you only:

   ```bash
   (umask 077; printf 'export TRITONAI_API_KEY=%s\n' '<paste key here>' > ~/.mccr_env)
   source ~/.mccr_env
   ```

   Never put this key in the repo or in `.env`.

## Keep GitHub as the source of truth

The instance can be stopped, lost or deleted, so GitHub holds the code.

Save work from the instance:

```bash
cd ~/mcc-recovery
git status
git add <files>
git commit -m "<message>"
git push origin main
```

Get work that was pushed from your Mac:

```bash
git pull origin main
```

Do not edit the same file on both machines without pushing first, or you will get merge conflicts.

### The sync routine (in this order)

Code and docs are written on the Mac. Result files are created on the instance. So changes travel both ways, and the order matters.

1. **Mac: commit and push** everything you changed.

   ```bash
   git status
   git add <files>
   git commit -m "<message>"
   git push origin main
   ```

2. **Instance: pull**, before you run anything, so the instance runs the same code as GitHub.

   ```bash
   cd ~/mcc-recovery && git pull origin main
   ```

3. **Instance: run the experiments.**

4. **Instance: pull again, then commit and push the result files.** The Mac may have pushed while the run was going.

   ```bash
   cd ~/mcc-recovery
   git pull origin main
   git status --short
   git add results/
   git commit -m "Add <what> result files"
   git push origin main
   ```

   `git status --short` should list only files under `results/`. Anything else is a file you did not mean to commit.

5. **Mac: pull**, so the Mac has the result files too.

   ```bash
   git pull origin main
   ```

Rules that keep this safe:
- **Through git:** code, docs, config, prompts, tasks, scripts, tests, and the small files in `results/`.
- **Never through git:** `runs/` (large; see below), `.env`, `~/.mccr_env`, keys, and `.venv/`.
- **Pull before every push, on both machines.** If `git push` says it was rejected, run `git pull origin main` and push again.
- **One machine edits a given file between syncs.** The Mac edits code and docs. The instance only adds files under `results/`. If you edit code on the instance (for example in VS Code), commit and push it right away, and pull on the Mac before you edit there.
- **Give every result file a new name** (for example `poc_gate2.json`, `poc2_tables/`). Do not overwrite an old result file.
- **"untracked working tree files would be overwritten"** on a pull means a file with that name exists on this machine but git does not track it yet. Move it aside (`mv results/<file> ~/`), pull, and compare. Or commit it first and push.
- **A merge conflict:** stop and ask. Do not force-push.

## Get results off the instance

`runs/` is not in git, because runs are large. The small files in `results/` go through git (see the sync routine above). Copy the run folders to your Mac only if you want a local copy for analysis (run on the Mac, in the repo folder; git ignores `runs/`):

```bash
rsync -az mccr:~/mcc-recovery/runs/ ./runs/
```

`scripts/sync_s3.sh` also exists, but our account has no S3 bucket yet and we have not checked that we may create one.

## Costs and rules

- Stop the instance when you are not running experiments.
- The AWS budget is $200 in total and $20 per day. One running instance costs about $2 per day.
- No real secrets are ever stored on the instance except the TritonAI key in `~/.mccr_env`. The AWS keys stay on your Mac.
