#!/usr/bin/env bash
# A short-lived Windows machine for Power BI Desktop, which only runs on Windows.
#   up      create it, install Power BI Desktop and copy the project and data onto it
#   fetch   copy the saved .pbix and PDF back into powerbi/
#   down    delete everything this script created
# Everything is tagged Project=retail-analysis. RDP is open to the caller's current IP only.
set -euo pipefail

export AWS_REGION=eu-west-2
NAME=retail-analysis-pbi
TAG="Key=Project,Value=retail-analysis"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="retail-analysis-transfer-$ACCOUNT"
KEY_FILE="$HOME/.ssh/$NAME.pem"

instance_id() {
  aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query "Reservations[].Instances[].InstanceId" --output text
}

run_ps() {  # run PowerShell on the machine through SSM and print its output
  local id cmd
  id=$(instance_id)
  cmd=$(aws ssm send-command --instance-ids "$id" --document-name AWS-RunPowerShellScript \
    --parameters "$(jq -n --arg c "$1" '{commands: [$c], executionTimeout: ["3600"]}')" \
    --timeout-seconds 3600 --query Command.CommandId --output text)
  # The built-in waiter gives up after a few minutes; a large download takes longer.
  while case "$(aws ssm get-command-invocation --command-id "$cmd" --instance-id "$id" --query Status --output text 2>/dev/null)" in
      Pending|InProgress|Delayed|"") true ;; *) false ;; esac; do sleep 15; done
  aws ssm get-command-invocation --command-id "$cmd" --instance-id "$id" \
    --query "{status:Status,out:StandardOutputContent,err:StandardErrorContent}" --output json
}

up() {
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint=$AWS_REGION >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{$TAG}]"
  aws s3 sync "$ROOT/data/powerbi" "s3://$BUCKET/data/" --quiet
  aws s3 sync "$ROOT/powerbi" "s3://$BUCKET/project/" --exclude "*.py" --exclude "base-theme/*" --quiet

  aws iam create-role --role-name "$NAME" --tags "$TAG" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$NAME" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam put-role-policy --role-name "$NAME" --policy-name transfer --policy-document "$(jq -n --arg b "$BUCKET" '{
    Version: "2012-10-17", Statement: [
      {Effect: "Allow", Action: ["s3:ListBucket"], Resource: "arn:aws:s3:::\($b)"},
      {Effect: "Allow", Action: ["s3:GetObject", "s3:PutObject"], Resource: "arn:aws:s3:::\($b)/*"}]}')"
  aws iam create-instance-profile --instance-profile-name "$NAME" --tags "$TAG" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$NAME" --role-name "$NAME"

  mkdir -p "$HOME/.ssh"
  aws ec2 create-key-pair --key-name "$NAME" --key-type rsa --key-format pem \
    --tag-specifications "ResourceType=key-pair,Tags=[{$TAG}]" --query KeyMaterial --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"

  local vpc sg ip ami
  vpc=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query "Vpcs[0].VpcId" --output text)
  sg=$(aws ec2 create-security-group --group-name "$NAME" --description "RDP from one address" --vpc-id "$vpc" \
    --tag-specifications "ResourceType=security-group,Tags=[{$TAG}]" --query GroupId --output text)
  ip=$(curl -s https://checkip.amazonaws.com)
  aws ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port 3389 --cidr "$ip/32" >/dev/null
  ami=$(aws ssm get-parameter --name /aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base \
    --query Parameter.Value --output text)

  sleep 10  # a new instance profile takes a few seconds to become usable
  aws ec2 run-instances --image-id "$ami" --instance-type m7i-flex.large --key-name "$NAME" --security-group-ids "$sg" \
    --iam-instance-profile "Name=$NAME" --metadata-options HttpTokens=required \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":60,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{$TAG}]" "ResourceType=volume,Tags=[{$TAG}]" \
    --query "Instances[0].InstanceId" --output text
  aws ec2 wait instance-status-ok --instance-ids "$(instance_id)"
  until [ "$(aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$(instance_id)" \
      --query 'length(InstanceInformationList)' --output text)" = "1" ]; do sleep 15; done

  run_ps "
    New-Item -ItemType Directory -Force C:\\retail\\powerbi, C:\\retail\\project | Out-Null
    Read-S3Object -BucketName $BUCKET -KeyPrefix data -Folder C:\\retail\\powerbi -Region $AWS_REGION | Out-Null
    Read-S3Object -BucketName $BUCKET -KeyPrefix project -Folder C:\\retail\\project -Region $AWS_REGION | Out-Null
    \$ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest 'https://download.microsoft.com/download/8/8/0/880BCA75-79DD-466A-927D-1ABF1F5454B0/PBIDesktopSetup_x64.exe' -OutFile C:\\retail\\PBIDesktopSetup_x64.exe
    Start-Process C:\\retail\\PBIDesktopSetup_x64.exe -ArgumentList '-quiet','-norestart','ACCEPT_EULA=1' -Wait
    Get-ChildItem C:\\retail\\powerbi | Select-Object Name, Length | Format-Table -AutoSize | Out-String
    Get-ChildItem 'C:\\Program Files\\Microsoft Power BI Desktop\\bin\\PBIDesktop.exe' | Select-Object FullName, @{n='Version';e={\$_.VersionInfo.ProductVersion}} | Format-List | Out-String
  "
  echo "Public address: $(aws ec2 describe-instances --instance-ids "$(instance_id)" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
  echo "User: Administrator. Password: run scripts/powerbi_vm.sh password (copies it to the clipboard)"
}

password() {  # copied to the clipboard, never printed
  aws ec2 get-password-data --instance-id "$(instance_id)" --priv-launch-key "$KEY_FILE" --query PasswordData --output text \
    | tr -d '\n' | pbcopy
  echo "Administrator password copied to the clipboard."
}

fetch() {
  run_ps "Get-ChildItem C:\\retail\\project -Recurse -Include *.pbix,*.pdf | ForEach-Object { Write-S3Object -BucketName $BUCKET -Key (\"out/\" + \$_.Name) -File \$_.FullName -Region $AWS_REGION; \$_.Name }"
  aws s3 sync "s3://$BUCKET/out/" "$ROOT/powerbi/" --quiet
  ls -la "$ROOT"/powerbi/*.pbix "$ROOT"/powerbi/*.pdf 2>/dev/null || true
}

down() {
  local id sg
  id=$(instance_id)
  if [ -n "$id" ]; then aws ec2 terminate-instances --instance-ids $id >/dev/null; aws ec2 wait instance-terminated --instance-ids $id; fi
  sg=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" --query "SecurityGroups[0].GroupId" --output text)
  [ "$sg" != "None" ] && aws ec2 delete-security-group --group-id "$sg"
  aws ec2 delete-key-pair --key-name "$NAME" >/dev/null 2>&1 || true
  rm -f "$KEY_FILE"
  aws iam remove-role-from-instance-profile --instance-profile-name "$NAME" --role-name "$NAME" 2>/dev/null || true
  aws iam delete-instance-profile --instance-profile-name "$NAME" 2>/dev/null || true
  aws iam detach-role-policy --role-name "$NAME" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore 2>/dev/null || true
  aws iam delete-role-policy --role-name "$NAME" --policy-name transfer 2>/dev/null || true
  aws iam delete-role --role-name "$NAME" 2>/dev/null || true
  aws s3 rb "s3://$BUCKET" --force >/dev/null 2>&1 || true
  echo "left behind, by tag:"
  aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=retail-analysis \
    --query "ResourceTagMappingList[].ResourceARN" --output text
}

"${1:?usage: $0 up|password|fetch|down}"
