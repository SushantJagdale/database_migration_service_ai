# Pre-Migration Report for MySQL

## RDS Instance Metadata
- **DBInstanceIdentifier:** gemini-mysql-instance-1
- **DBInstanceClass:** db.t3.micro
- **Engine:** mysql
- **DBInstanceStatus:** available
- **MasterUsername:** admin
- **Endpoint:** {'Address': 'gemini-mysql-instance-1.cn6yiussieyt.ap-south-1.rds.amazonaws.com', 'Port': 3306, 'HostedZoneId': 'Z2VFMSZA74J7XZ'}
- **AllocatedStorage:** 20
- **InstanceCreateTime:** 2026-01-19 07:32:07.189000+00:00
- **PreferredBackupWindow:** 22:07-22:37
- **BackupRetentionPeriod:** 1
- **DBSecurityGroups:** []
- **VpcSecurityGroups:** [{'VpcSecurityGroupId': 'sg-090c27c091f9adce0', 'Status': 'active'}]
- **DBParameterGroups:** [{'DBParameterGroupName': 'default.mysql8.0', 'ParameterApplyStatus': 'in-sync'}]
- **AvailabilityZone:** ap-south-1c
- **DBSubnetGroup:** {'DBSubnetGroupName': 'default', 'DBSubnetGroupDescription': 'default', 'VpcId': 'vpc-0dec259170dbba849', 'SubnetGroupStatus': 'Complete', 'Subnets': [{'SubnetIdentifier': 'subnet-045657662c6bc71ec', 'SubnetAvailabilityZone': {'Name': 'ap-south-1b'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0e3ab611ca7663d9b', 'SubnetAvailabilityZone': {'Name': 'ap-south-1a'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0b65a0dd5917db7a4', 'SubnetAvailabilityZone': {'Name': 'ap-south-1c'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}]}
- **PreferredMaintenanceWindow:** sun:09:36-sun:10:06
- **UpgradeRolloutOrder:** second
- **PendingModifiedValues:** {}
- **LatestRestorableTime:** 2026-04-21 10:23:18+00:00
- **MultiAZ:** False
- **EngineVersion:** 8.0.44
- **AutoMinorVersionUpgrade:** True
- **ReadReplicaDBInstanceIdentifiers:** []
- **LicenseModel:** general-public-license
- **StorageThroughput:** 0
- **OptionGroupMemberships:** [{'OptionGroupName': 'default:mysql-8-0', 'Status': 'in-sync'}]
- **PubliclyAccessible:** True
- **StorageType:** gp2
- **DbInstancePort:** 0
- **StorageEncrypted:** False
- **DbiResourceId:** db-HLIIJZMU5CKGKIGLKI7LHGJG6I
- **CACertificateIdentifier:** rds-ca-rsa2048-g1
- **DomainMemberships:** []
- **CopyTagsToSnapshot:** False
- **MonitoringInterval:** 0
- **DBInstanceArn:** arn:aws:rds:ap-south-1:823722174366:db:gemini-mysql-instance-1
- **IAMDatabaseAuthenticationEnabled:** False
- **DatabaseInsightsMode:** standard
- **PerformanceInsightsEnabled:** False
- **DeletionProtection:** False
- **AssociatedRoles:** []
- **TagList:** []
- **CustomerOwnedIpEnabled:** False
- **NetworkType:** IPV4
- **ActivityStreamStatus:** stopped
- **BackupTarget:** region
- **CertificateDetails:** {'CAIdentifier': 'rds-ca-rsa2048-g1', 'ValidTill': datetime.datetime(2027, 1, 19, 7, 30, 44, tzinfo=tzutc())}
- **DedicatedLogVolume:** False
- **IsStorageConfigUpgradeAvailable:** False
- **EngineLifecycleSupport:** open-source-rds-extended-support
- **Region:** ap-south-1

## Prerequisite Checks
| Check | Status |
|---|---|
| Version Check | PASS: Compatible. |
| Replication Params | FAIL: log_bin is 'Not Set'. It must be 'ON'.<br>FAIL: binlog_format is 'MIXED'. It must be 'ROW'. |
| Table Case Sensitivity | INFO: lower_case_table_names is not explicitly set. Defaults should be compatible. |
| Packet Size | INFO: max_allowed_packet is not explicitly set. Consider setting it to 256M or higher. |

## Suggested Alterations
No alterations needed.
# Pre-Migration Report for MySQL

## RDS Instance Metadata
- **DBInstanceIdentifier:** gemini-mysql-instance-2
- **DBInstanceClass:** db.t3.micro
- **Engine:** mysql
- **DBInstanceStatus:** available
- **MasterUsername:** admin
- **Endpoint:** {'Address': 'gemini-mysql-instance-2.cn6yiussieyt.ap-south-1.rds.amazonaws.com', 'Port': 3306, 'HostedZoneId': 'Z2VFMSZA74J7XZ'}
- **AllocatedStorage:** 20
- **InstanceCreateTime:** 2026-01-19 07:32:04.231000+00:00
- **PreferredBackupWindow:** 21:40-22:10
- **BackupRetentionPeriod:** 1
- **DBSecurityGroups:** []
- **VpcSecurityGroups:** [{'VpcSecurityGroupId': 'sg-090c27c091f9adce0', 'Status': 'active'}]
- **DBParameterGroups:** [{'DBParameterGroupName': 'default.mysql8.0', 'ParameterApplyStatus': 'in-sync'}]
- **AvailabilityZone:** ap-south-1a
- **DBSubnetGroup:** {'DBSubnetGroupName': 'default', 'DBSubnetGroupDescription': 'default', 'VpcId': 'vpc-0dec259170dbba849', 'SubnetGroupStatus': 'Complete', 'Subnets': [{'SubnetIdentifier': 'subnet-045657662c6bc71ec', 'SubnetAvailabilityZone': {'Name': 'ap-south-1b'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0e3ab611ca7663d9b', 'SubnetAvailabilityZone': {'Name': 'ap-south-1a'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0b65a0dd5917db7a4', 'SubnetAvailabilityZone': {'Name': 'ap-south-1c'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}]}
- **PreferredMaintenanceWindow:** sun:06:58-sun:07:28
- **UpgradeRolloutOrder:** second
- **PendingModifiedValues:** {}
- **LatestRestorableTime:** 2026-04-21 10:20:37+00:00
- **MultiAZ:** False
- **EngineVersion:** 8.0.44
- **AutoMinorVersionUpgrade:** True
- **ReadReplicaDBInstanceIdentifiers:** []
- **LicenseModel:** general-public-license
- **StorageThroughput:** 0
- **OptionGroupMemberships:** [{'OptionGroupName': 'default:mysql-8-0', 'Status': 'in-sync'}]
- **PubliclyAccessible:** True
- **StorageType:** gp2
- **DbInstancePort:** 0
- **StorageEncrypted:** False
- **DbiResourceId:** db-F2IWLAR2S6BXPEA5SGQGIFBHG4
- **CACertificateIdentifier:** rds-ca-rsa2048-g1
- **DomainMemberships:** []
- **CopyTagsToSnapshot:** False
- **MonitoringInterval:** 0
- **DBInstanceArn:** arn:aws:rds:ap-south-1:823722174366:db:gemini-mysql-instance-2
- **IAMDatabaseAuthenticationEnabled:** False
- **DatabaseInsightsMode:** standard
- **PerformanceInsightsEnabled:** False
- **DeletionProtection:** False
- **AssociatedRoles:** []
- **TagList:** []
- **CustomerOwnedIpEnabled:** False
- **NetworkType:** IPV4
- **ActivityStreamStatus:** stopped
- **BackupTarget:** region
- **CertificateDetails:** {'CAIdentifier': 'rds-ca-rsa2048-g1', 'ValidTill': datetime.datetime(2027, 1, 19, 7, 30, 36, tzinfo=tzutc())}
- **DedicatedLogVolume:** False
- **IsStorageConfigUpgradeAvailable:** False
- **EngineLifecycleSupport:** open-source-rds-extended-support
- **Region:** ap-south-1

## Prerequisite Checks
| Check | Status |
|---|---|
| Version Check | PASS: Compatible. |
| Replication Params | FAIL: log_bin is 'Not Set'. It must be 'ON'.<br>FAIL: binlog_format is 'MIXED'. It must be 'ROW'. |
| Table Case Sensitivity | INFO: lower_case_table_names is not explicitly set. Defaults should be compatible. |
| Packet Size | INFO: max_allowed_packet is not explicitly set. Consider setting it to 256M or higher. |

## Suggested Alterations
No alterations needed.
