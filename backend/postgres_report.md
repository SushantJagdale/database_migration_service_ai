# Pre-Migration Report for PostgreSQL

## RDS Instance Metadata
- **DBInstanceIdentifier:** gemini-postgres-instance-1
- **DBInstanceClass:** db.t3.micro
- **Engine:** postgres
- **DBInstanceStatus:** available
- **MasterUsername:** postgres
- **Endpoint:** {'Address': 'gemini-postgres-instance-1.cn6yiussieyt.ap-south-1.rds.amazonaws.com', 'Port': 5432, 'HostedZoneId': 'Z2VFMSZA74J7XZ'}
- **AllocatedStorage:** 20
- **InstanceCreateTime:** 2026-01-19 07:32:00.486000+00:00
- **PreferredBackupWindow:** 21:52-22:22
- **BackupRetentionPeriod:** 1
- **DBSecurityGroups:** []
- **VpcSecurityGroups:** [{'VpcSecurityGroupId': 'sg-090c27c091f9adce0', 'Status': 'active'}]
- **DBParameterGroups:** [{'DBParameterGroupName': 'default.postgres17', 'ParameterApplyStatus': 'in-sync'}]
- **AvailabilityZone:** ap-south-1c
- **DBSubnetGroup:** {'DBSubnetGroupName': 'default', 'DBSubnetGroupDescription': 'default', 'VpcId': 'vpc-0dec259170dbba849', 'SubnetGroupStatus': 'Complete', 'Subnets': [{'SubnetIdentifier': 'subnet-045657662c6bc71ec', 'SubnetAvailabilityZone': {'Name': 'ap-south-1b'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0e3ab611ca7663d9b', 'SubnetAvailabilityZone': {'Name': 'ap-south-1a'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0b65a0dd5917db7a4', 'SubnetAvailabilityZone': {'Name': 'ap-south-1c'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}]}
- **PreferredMaintenanceWindow:** fri:06:51-fri:07:21
- **UpgradeRolloutOrder:** second
- **PendingModifiedValues:** {}
- **LatestRestorableTime:** 2026-04-21 10:19:34+00:00
- **MultiAZ:** False
- **EngineVersion:** 17.6
- **AutoMinorVersionUpgrade:** True
- **ReadReplicaDBInstanceIdentifiers:** []
- **LicenseModel:** postgresql-license
- **StorageThroughput:** 0
- **OptionGroupMemberships:** [{'OptionGroupName': 'default:postgres-17', 'Status': 'in-sync'}]
- **PubliclyAccessible:** True
- **StorageType:** gp2
- **DbInstancePort:** 0
- **StorageEncrypted:** False
- **DbiResourceId:** db-FG3H3JKBCSHKZBA77FWFDBAKXY
- **CACertificateIdentifier:** rds-ca-rsa2048-g1
- **DomainMemberships:** []
- **CopyTagsToSnapshot:** False
- **MonitoringInterval:** 0
- **DBInstanceArn:** arn:aws:rds:ap-south-1:823722174366:db:gemini-postgres-instance-1
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
| Version Check | FAIL: Not compatible. Must be one of ['10', '11', '12', '13', '14', '15']. |
| Logical Replication | FAIL: wal_level is 'Not Set'. It must be 'logical'.<br>PASS: max_replication_slots is set to 20. |
| Worker Processes & Locks | PASS: max_wal_senders is set to a reasonable value (35).<br>FAIL: max_worker_processes is '0'. It should be >= 8.<br>FAIL: max_locks_per_transaction is '0'. It should be >= 64. |

## Suggested Alterations
No alterations needed.
# Pre-Migration Report for PostgreSQL

## RDS Instance Metadata
- **DBInstanceIdentifier:** gemini-postgres-instance-2
- **DBInstanceClass:** db.t3.micro
- **Engine:** postgres
- **DBInstanceStatus:** available
- **MasterUsername:** postgres
- **Endpoint:** {'Address': 'gemini-postgres-instance-2.cn6yiussieyt.ap-south-1.rds.amazonaws.com', 'Port': 5432, 'HostedZoneId': 'Z2VFMSZA74J7XZ'}
- **AllocatedStorage:** 20
- **InstanceCreateTime:** 2026-01-19 07:32:02.841000+00:00
- **PreferredBackupWindow:** 16:35-17:05
- **BackupRetentionPeriod:** 1
- **DBSecurityGroups:** []
- **VpcSecurityGroups:** [{'VpcSecurityGroupId': 'sg-090c27c091f9adce0', 'Status': 'active'}]
- **DBParameterGroups:** [{'DBParameterGroupName': 'default.postgres17', 'ParameterApplyStatus': 'in-sync'}]
- **AvailabilityZone:** ap-south-1b
- **DBSubnetGroup:** {'DBSubnetGroupName': 'default', 'DBSubnetGroupDescription': 'default', 'VpcId': 'vpc-0dec259170dbba849', 'SubnetGroupStatus': 'Complete', 'Subnets': [{'SubnetIdentifier': 'subnet-045657662c6bc71ec', 'SubnetAvailabilityZone': {'Name': 'ap-south-1b'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0e3ab611ca7663d9b', 'SubnetAvailabilityZone': {'Name': 'ap-south-1a'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}, {'SubnetIdentifier': 'subnet-0b65a0dd5917db7a4', 'SubnetAvailabilityZone': {'Name': 'ap-south-1c'}, 'SubnetOutpost': {}, 'SubnetStatus': 'Active'}]}
- **PreferredMaintenanceWindow:** mon:09:23-mon:09:53
- **UpgradeRolloutOrder:** second
- **PendingModifiedValues:** {}
- **LatestRestorableTime:** 2026-04-21 10:20:41+00:00
- **MultiAZ:** False
- **EngineVersion:** 17.6
- **AutoMinorVersionUpgrade:** True
- **ReadReplicaDBInstanceIdentifiers:** []
- **LicenseModel:** postgresql-license
- **StorageThroughput:** 0
- **OptionGroupMemberships:** [{'OptionGroupName': 'default:postgres-17', 'Status': 'in-sync'}]
- **PubliclyAccessible:** True
- **StorageType:** gp2
- **DbInstancePort:** 0
- **StorageEncrypted:** False
- **DbiResourceId:** db-KPTR2HYMMLECGOE5PG755OMYNQ
- **CACertificateIdentifier:** rds-ca-rsa2048-g1
- **DomainMemberships:** []
- **CopyTagsToSnapshot:** False
- **MonitoringInterval:** 0
- **DBInstanceArn:** arn:aws:rds:ap-south-1:823722174366:db:gemini-postgres-instance-2
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
- **CertificateDetails:** {'CAIdentifier': 'rds-ca-rsa2048-g1', 'ValidTill': datetime.datetime(2027, 1, 19, 7, 30, 45, tzinfo=tzutc())}
- **DedicatedLogVolume:** False
- **IsStorageConfigUpgradeAvailable:** False
- **EngineLifecycleSupport:** open-source-rds-extended-support
- **Region:** ap-south-1

## Prerequisite Checks
| Check | Status |
|---|---|
| Version Check | FAIL: Not compatible. Must be one of ['10', '11', '12', '13', '14', '15']. |
| Logical Replication | FAIL: wal_level is 'Not Set'. It must be 'logical'.<br>PASS: max_replication_slots is set to 20. |
| Worker Processes & Locks | PASS: max_wal_senders is set to a reasonable value (35).<br>FAIL: max_worker_processes is '0'. It should be >= 8.<br>FAIL: max_locks_per_transaction is '0'. It should be >= 64. |

## Suggested Alterations
No alterations needed.
