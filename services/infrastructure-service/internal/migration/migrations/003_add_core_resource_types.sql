ALTER TABLE infrastructure_resources
    DROP CONSTRAINT IF EXISTS infrastructure_resources_resource_type_check;

ALTER TABLE infrastructure_resources
    ADD CONSTRAINT infrastructure_resources_resource_type_check
    CHECK (
        resource_type IS NULL
        OR resource_type IN (
            'aws_vpc',
            'aws_ec2',
            'aws_s3',
            'aws_rds',
            'aws_eks',
            'aws_lb'
        )
    );
